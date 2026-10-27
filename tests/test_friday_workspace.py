import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from core.friday_workspace import Workspace, analyze_csv, verify_artifact, check_media_brief
from core.friday_operator import artifact_destination, browser_action, finish_step, needs_approval, safe_url


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = Workspace(self.root, self.root / "outputs")
        self.enqueue = patch.object(self.store, "_enqueue")
        self.enqueue.start()

    def tearDown(self):
        self.enqueue.stop()
        self.temp.cleanup()

    def job(self, **kw):
        return self.store.submit("Prepare the requested deliverable", **kw)

    def test_brand_snapshot_and_plan_are_durable(self):
        self.store.save_brand("Shop", {"audience": "Gardeners", "facts": "Steel", "password": "excluded"})
        steps = [{"service": "Claude", "instruction": "Research"}, {"service": "ChatGPT", "instruction": "Write copy"}]
        job = self.job(brand="Shop", steps=steps)
        steps[0]["instruction"] = "Changed"
        self.store.save_brand("Shop", {"audience": "Someone else"})
        actual = self.store.get(job["id"])
        self.assertEqual(actual["steps"][0]["instruction"], "Research")
        self.assertEqual(actual["brand_context"]["audience"], "Gardeners")
        self.assertNotIn("password", actual["brand_context"])

    def test_restart_pauses_unfinished_jobs(self):
        job = self.job()
        self.store.update(job["id"], status="running")
        restored = Workspace(self.root, self.root / "outputs")
        self.assertEqual(restored.get(job["id"])["status"], "paused")

    def test_cancel_cannot_be_overwritten_by_worker(self):
        job = self.job()
        self.store.cancel(job["id"])
        self.store.update(job["id"], status="completed", message="wrong")
        self.assertEqual(self.store.get(job["id"])["status"], "cancelled")

    def test_approval_not_granted_by_voice_resume(self):
        job = self.job()
        self.store.update(job["id"], status="waiting_user", pending_action={"token": "abc", "action": {"action": "click"}})
        with self.assertRaisesRegex(ValueError, "Approve"):
            self.store.resume(job["id"])

    def test_invalid_attachments_and_services_rejected(self):
        with self.assertRaises(ValueError):
            self.job(files=[str(self.root / "missing.mp4")])
        with self.assertRaises(ValueError):
            self.job(service="Unknown")
        with self.assertRaises(ValueError):
            self.job(steps=[{"service": "Gemini"}])

    def test_required_media_cannot_be_replaced_with_report(self):
        job = self.job(workflow="image")
        Path(job["output"]).mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, "media file"):
            finish_step(self.store, job["id"], {"report": "Here is a prompt."}, set())

    def test_handoff_adds_report_as_next_attachment(self):
        job = self.job(steps=[{"service": "Claude", "instruction": "Research"}, {"service": "ChatGPT", "instruction": "Write"}])
        Path(job["output"]).mkdir(parents=True)
        finish_step(self.store, job["id"], {"report": "Research facts and sources."}, set())
        actual = self.store.get(job["id"])
        self.assertEqual(actual["step"], 1)
        self.assertTrue(Path(actual["files"][0]).is_file())

    def test_image_verification_and_empty_rejection(self):
        from PIL import Image
        image = self.root / "image.png"
        Image.new("RGB", (40, 30)).save(image)
        result = verify_artifact(image)
        self.assertEqual(result["dimensions"], [40, 30])
        self.assertEqual(len(result["sha256"]), 64)
        empty = self.root / "empty.png"
        empty.touch()
        with self.assertRaises(ValueError):
            verify_artifact(empty)
        corrupt = self.root / "corrupt.png"
        corrupt.write_text("Not an image")
        with self.assertRaises(Exception):
            verify_artifact(corrupt)

    def test_analytics_real_calculation_and_missing_metrics(self):
        path = self.root / "ads.csv"
        path.write_text("spend,impressions,clicks,orders,revenue\n100,1000,50,5,400\n50,500,25,1,100\n")
        outputs = analyze_csv(path, self.root / "reports")
        report = json.loads(Path(outputs[0]["path"]).read_text())
        self.assertEqual(report["totals"]["spend"], 150)
        self.assertEqual(report["metrics"]["CTR (%)"], 5)
        self.assertAlmostEqual(report["metrics"]["ROAS"], 500/150)
        self.assertIsNone(report["metrics"]["CPL"])

    def test_analytics_rejects_blank_nan_negative_and_empty(self):
        for content in ["spend,orders\n,1\n", "spend\nnan\n", "spend\n-1\n", "spend\n"]:
            path = self.root / "bad.csv"
            path.write_text(content)
            with self.assertRaises(ValueError):
                analyze_csv(path, self.root / "bad-report")

    def test_analytics_background_job_completes_with_manifest(self):
        self.enqueue.stop()
        path = self.root / "ads.csv"
        path.write_text("spend,revenue\n10,30\n")
        job = self.job(workflow="analytics", files=[str(path)])
        deadline = time.monotonic() + 5
        while self.store.get(job["id"])["status"] not in {"completed", "failed"} and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertEqual(self.store.get(job["id"])["status"], "completed")
        self.assertTrue((Path(job["output"]) / "delivery.json").exists())
        if self.store.worker:
            self.store.worker.join(2)

    def test_paths_and_urls_reject_unsafe_navigation(self):
        self.assertEqual(artifact_destination(self.root, "../../asset.png").parent, self.root)
        for url in ["file:///etc/passwd", "javascript:alert(1)", "https://user:secret@example.com"]:
            with self.assertRaises(ValueError):
                safe_url(url)
        self.assertEqual(safe_url("https://example.com"), "https://example.com")

    def test_commit_buttons_require_review_but_ai_send_does_not(self):
        observed = {"elements": [{"text": "Publish"}, {"text": "Send prompt"}]}
        self.assertTrue(needs_approval({"action": "click", "index": 0}, observed))
        self.assertFalse(needs_approval({"action": "click", "index": 1}, observed))
        self.assertTrue(needs_approval({"action": "type", "risk": "external_commit"}, observed))

    def test_negative_control_index_cannot_select_last_element(self):
        class Page:
            _friday_handles = [object()]
        with self.assertRaises(ValueError):
            browser_action(Page(), {"action": "click", "index": -1}, {"files": []})

    def test_explicit_media_dimensions_and_duration_are_checked(self):
        job = {"workflow": "video", "goal": "Make a 30-second 1080x1920 video", "artifacts": [
            {"path": "video.mp4", "dimensions": [1080, 1920], "duration_seconds": 30.1}]}
        check_media_brief(job)
        job["artifacts"][0]["duration_seconds"] = 80
        with self.assertRaisesRegex(ValueError, "duration"):
            check_media_brief(job)
        job["artifacts"][0]["dimensions"] = [1920, 1080]
        with self.assertRaisesRegex(ValueError, "dimensions"):
            check_media_brief(job)

    def test_voice_status_resume_cancel_need_no_identifier(self):
        from actions.marketing_workspace import marketing_workspace
        job = self.job()
        self.store.update(job["id"], status="paused")
        with patch("actions.marketing_workspace.get_workspace", return_value=self.store):
            result = json.loads(marketing_workspace({"action": "status"}))
            self.assertEqual(result["id"], job["id"])
            result = json.loads(marketing_workspace({"action": "resume"}))
            self.assertEqual(result["status"], "queued")
            result = json.loads(marketing_workspace({"action": "cancel"}))
            self.assertEqual(result["status"], "cancelled")

    def test_original_hud_approval_can_resume_waiting_job(self):
        from core import confirm
        job = self.job()
        self.store.update(job["id"], status="running")
        self.store.active = job["id"]
        done = []
        banners = []
        confirm.bind(lambda title, detail: banners.append((title, detail)), lambda: None)
        thread = threading.Thread(target=lambda: done.append(self.store.wait_for_user(
            job["id"], "Publish the reviewed campaign", {"action": "click", "index": 0})))
        thread.start()
        deadline = time.monotonic() + 2
        while not banners and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertTrue(banners)
        confirm.resolve(True)
        thread.join(3)
        self.assertEqual(done, [True])
        self.assertEqual(self.store.get(job["id"])["status"], "running")
        confirm.bind(None, None)

    def test_spoken_confirmation_is_specific_single_use_and_expires(self):
        from core import confirm
        completed = threading.Event()
        confirm.bind(lambda title, detail: None, lambda: None)
        confirm.request("test", "Test action", "Test detail", lambda: completed.set())
        hint = confirm.voice_instruction()
        phrase = hint.split("Say ", 1)[1].split(" to approve", 1)[0]
        self.assertFalse(confirm.resolve_spoken_input("yes"))
        self.assertFalse(confirm.resolve_spoken_input("Friday confirm wrong words"))
        self.assertTrue(confirm.resolve_spoken_input(phrase))
        self.assertTrue(completed.wait(2))
        self.assertFalse(confirm.resolve_spoken_input(phrase))
        confirm.request("expired", "Expired action", "Test detail", lambda: None)
        hint = confirm.voice_instruction()
        phrase = hint.split("Say ", 1)[1].split(" to approve", 1)[0]
        with patch("core.confirm.time.monotonic", return_value=time.monotonic() + 1000):
            self.assertFalse(confirm.resolve_spoken_input(phrase))
        confirm.resolve(False)
        confirm.bind(None, None)

    def test_spoken_cancel_does_not_execute_protected_action(self):
        from core import confirm
        executed, cancelled = threading.Event(), threading.Event()
        confirm.bind(lambda title, detail: None, lambda: None)
        confirm.request("cancel", "Test", "Details", lambda: executed.set(), on_cancel=cancelled.set)
        self.assertTrue(confirm.resolve_spoken_input("Friday cancel action"))
        self.assertTrue(cancelled.wait(2))
        self.assertFalse(executed.is_set())
        confirm.bind(None, None)


if __name__ == "__main__":
    unittest.main()
