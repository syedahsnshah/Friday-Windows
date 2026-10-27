"""Real Chrome, local AI-service fixtures, scripted model decisions."""
import io
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from PIL import Image

from core.friday_workspace import Workspace
from existing_browser_fixture import attach_fixture_context
from core.friday_operator import run_job


@unittest.skipUnless(bool(os.environ.get("FRIDAY_EXISTING_CDP")), "Needs an existing debug-enabled Chrome; never launches browsers")
class WorkflowIntegration(unittest.TestCase):
    def test_pause_resume_without_duplicate_prompt_then_cross_service_file_handoff(self):
        state = {"research": 0, "image": 0}
        png = io.BytesIO()
        Image.new("RGB", (64, 64), "white").save(png, "PNG")
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_GET(self):
                if self.path.startswith("/sent?"):
                    stage = self.path.split("=",1)[1]
                    state[stage] += 1
                    self.send_response(200); self.end_headers(); self.wfile.write(b"ok")
                    return
                if self.path == "/product.png":
                    self.send_response(200)
                    self.send_header("Content-Type", "image/png")
                    self.send_header("Content-Disposition", 'attachment; filename="product.png"')
                    self.end_headers();self.wfile.write(png.getvalue())
                    return
                stage = "image" if self.path.startswith("/image") else "research"
                answer = "Competitor research: a plain ceramic mug, with a sourced positioning brief." if stage == "research" else "Finished product image"
                visible = "" if state[stage] else "hidden"
                html = f'''<html><title>{stage}</title><body>
                <textarea aria-label="Prompt"></textarea><input type="file" style="display:none">
                <button onclick="fetch('/sent?stage={stage}').then(()=>{{document.getElementById('answer').hidden=false;document.getElementById('download').hidden=false;}})">Send</button>
                <div id="answer" {visible}>{answer}</div><a id="download" {visible} href="/product.png" download>Download image</a>
                </body></html>'''
                self.send_response(200);self.send_header("Content-Type","text/html");self.end_headers();self.wfile.write(html.encode())
        server = ThreadingHTTPServer(("127.0.0.1",0),Handler)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                store=Workspace(directory,Path(directory)/"outputs")
                with patch.object(store,"_enqueue"):
                    job=store.submit("Research then create a square product image", "image", steps=[
                        {"service":"ChatGPT","instruction":"Research product positioning","output":"report"},
                        {"service":"Gemini","instruction":"Create finished product image","output":"image"}])
                Path(job["output"]).mkdir(parents=True)
                store.update(job["id"],status="running")
                paused=[False]
                def decide(current,instruction,image,observation):
                    step=current["step"]
                    receipt=current.get("receipts",{}).get(f"{step}:0",{})
                    if receipt.get("phase") != "sent":
                        return {"action":"submit_prompt","file_indices":[0] if step else [],"reason":"Send the saved brief once"}
                    if step==0:
                        if not paused[0]:
                            paused[0]=True
                            store.pause(current["id"])
                            return {"action":"click","index":observation["service_ui"]["send"]}
                        return {"action":"finish","report":"Competitor research: plain ceramic mug positioning. Source: local fixture."}
                    if not any(a["path"].endswith(".png") for a in current["artifacts"]):
                        return {"action":"click","index":observation["service_ui"]["downloads"][0]}
                    return {"action":"finish","report":"Finished product image downloaded."}
                review={"status":"passed","checks":[{"name":"Fixture output","status":"passed"}]}
                urls={"ChatGPT":f"http://127.0.0.1:{server.server_port}/research","Gemini":f"http://127.0.0.1:{server.server_port}/image"}
                with patch("core.friday_operator.open_existing_context", side_effect=attach_fixture_context), patch.dict("core.friday_operator.SERVICES",urls),patch("core.friday_operator.decide",side_effect=decide),patch("core.friday_operator.review_delivery",side_effect=lambda *args:dict(review)):
                    self.assertFalse(run_job(store,job["id"]))
                    self.assertEqual(state["research"],1)
                    self.assertEqual(store.get(job["id"])["status"],"paused")
                    with patch.object(store,"_enqueue"):
                        store.resume(job["id"])
                    store.update(job["id"],status="running")
                    self.assertTrue(run_job(store,job["id"]))
                actual=store.get(job["id"])
                self.assertEqual(state,{"research":1,"image":1})
                self.assertEqual(actual["step"],2)
                self.assertEqual(len(actual["artifacts"]),2)
                self.assertTrue(any(a.get("dimensions")==[64,64] for a in actual["artifacts"]))
                self.assertTrue(all(r["phase"]=="sent" for r in actual["receipts"].values()))
        finally:
            server.shutdown();server.server_close()
