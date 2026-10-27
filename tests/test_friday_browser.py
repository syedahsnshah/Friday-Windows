"""Opt-in local browser integration; no external AI account or network service."""
import io
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from existing_browser_fixture import attach_fixture_context
from core.friday_operator import run_job
from core.friday_workspace import Workspace


@unittest.skipUnless(bool(os.environ.get("FRIDAY_EXISTING_CDP")), "Needs an existing debug-enabled Chrome; never launches browsers")
class BrowserIntegration(unittest.TestCase):
    def test_prompt_hidden_upload_generation_and_real_download(self):
        image = io.BytesIO()
        Image.new("RGB", (32, 24), "blue").save(image, "PNG")
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_GET(self):
                if self.path == "/asset.png":
                    self.send_response(200)
                    self.send_header("Content-Type", "image/png")
                    self.send_header("Content-Disposition", 'attachment; filename="product.png"')
                    self.end_headers()
                    self.wfile.write(image.getvalue())
                else:
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html")
                    self.end_headers()
                    self.wfile.write(b'''<html><title>Local AI fixture</title><body>
                    <textarea aria-label="Prompt"></textarea><input type="file" style="display:none">
                    <button onclick="document.getElementById('download').hidden=false">Generate</button>
                    <a id="download" href="/asset.png" download hidden>Download image</a>
                    </body></html>''')
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as temp:
                store = Workspace(temp, Path(temp) / "output")
                attachment = Path(temp) / "brief.txt"
                attachment.write_text("Blue product")
                with patch.object(store, "_enqueue"):
                    job = store.submit("Create a blue product image", "image", files=[str(attachment)])
                Path(job["output"]).mkdir(parents=True)
                store.update(job["id"], status="running")
                calls = []
                def decision(job, instruction, screenshot, observation):
                    self.assertTrue(screenshot)
                    elements = observation["elements"]
                    n = len(calls)
                    calls.append(n)
                    if n == 0:
                        idx = next(i for i,e in enumerate(elements) if e["text"] == "Prompt")
                        return {"action": "type", "index": idx, "text": "Blue product"}
                    if n == 1:
                        idx = next(i for i,e in enumerate(elements) if e["type"] == "file")
                        return {"action": "upload", "index": idx, "file_index": 0}
                    if n == 2:
                        idx = next(i for i,e in enumerate(elements) if e["text"] == "Generate")
                        return {"action": "click", "index": idx}
                    if n == 3:
                        idx = next(i for i,e in enumerate(elements) if e["text"] == "Download image")
                        return {"action": "click", "index": idx}
                    return {"action": "finish", "report": "Generated product image downloaded from the local fixture."}
                with patch("core.friday_operator.open_existing_context", side_effect=attach_fixture_context), patch.dict("core.friday_operator.SERVICES", {"Gemini": f"http://127.0.0.1:{server.server_port}/"}), patch("core.friday_operator.decide", side_effect=decision), patch("core.friday_operator.review_delivery", return_value={"status": "passed", "checks": [{"name": "Fixture", "status": "passed"}]}):
                    self.assertTrue(run_job(store, job["id"]))
                actual = store.get(job["id"])
                image_artifact = next(a for a in actual["artifacts"] if a["path"].endswith(".png"))
                self.assertEqual(image_artifact["dimensions"], [32, 24])
                self.assertEqual(actual["step"], 1)
                self.assertEqual(len(actual["files"]), 2)
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
