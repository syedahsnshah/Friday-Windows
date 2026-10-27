import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from core.friday_workspace import Workspace, verify_artifact
from core.friday_services import basic_plan, plan_job, service_observation, validate_plan, build_prompt
from core.friday_quality import QualityIssue, objective_checks, review_delivery


class PlanningAndQualityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = Workspace(self.root, self.root / "outputs")
        self.enqueue = patch.object(self.store, "_enqueue")
        self.enqueue.start()
    def tearDown(self):
        self.store.scheduler_stop.set()
        self.enqueue.stop()
        self.temp.cleanup()

    def test_auto_campaign_plan_can_handoff_research_copy_and_image(self):
        plan = basic_plan("campaign", "Research a campaign and create product images", "Auto")
        self.assertEqual([p["output"] for p in plan], ["report", "report", "image"])
        self.assertEqual(plan[-1]["service"], "Gemini")

    def test_invalid_model_plan_falls_back_to_capabilities(self):
        job = self.store.submit("Create a video from my footage", "video", "Auto")
        with patch("core.gemini.as_json", return_value={"steps": [{"service": "Claude", "instruction": "Edit video", "output": "video"}]}):
            result = plan_job(job)
        self.assertEqual(result[-1]["service"], "CapCut")
        self.assertEqual(result[-1]["output"], "video")

    def test_unknown_plan_executor_rejected(self):
        with self.assertRaises(ValueError):
            validate_plan([{"service": "ChatGPT", "instruction": "Run a shell", "executor": "shell"}])

    def test_report_exports_are_followed_by_real_local_analytics(self):
        plan = basic_plan("analytics", "Analyze Meta Ads performance", "Auto")
        self.assertEqual(plan[0]["output"], "csv")
        self.assertEqual(plan[1]["executor"], "analytics")
        self.assertEqual(plan[1]["service"], "Local")

    def test_observed_service_controls_and_generation_state(self):
        observed = {"elements": [
            {"tag": "TEXTAREA", "text": "Message ChatGPT"},
            {"tag": "BUTTON", "text": "Send prompt"},
            {"tag": "INPUT", "type": "file", "text": ""},
            {"tag": "BUTTON", "text": "Stop generating"}], "text": ""}
        state = service_observation("ChatGPT", observed)
        self.assertEqual(state["composer"], 0)
        self.assertEqual(state["send"], 1)
        self.assertEqual(state["upload"], 2)
        self.assertTrue(state["generating"])

    def test_pause_resume_preserves_checkpoint(self):
        job = self.store.submit("Research competitors", "competitors")
        self.store.update(job["id"], status="running", checkpoint={"step": 0, "url": "https://example.com/conversation"})
        self.store.active = job["id"]
        self.assertEqual(self.store.pause(job["id"])["status"], "paused")
        resumed = self.store.resume(job["id"])
        self.assertEqual(resumed["status"], "queued")
        self.assertEqual(resumed["checkpoint"]["url"], "https://example.com/conversation")

    def test_scheduled_task_queues_once_and_pause_prevents_dispatch(self):
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        with patch.object(self.store, "start_scheduler"):
            job = self.store.submit("Research competitors", scheduled_at=future.isoformat())
        self.assertEqual(job["status"], "scheduled")
        self.assertFalse(self.store._enqueue.called)
        self.store.dispatch_due(future + timedelta(seconds=1))
        self.assertEqual(self.store.get(job["id"])["status"], "queued")
        self.assertEqual(self.store._enqueue.call_count, 1)
        self.store.dispatch_due(future + timedelta(seconds=2))
        self.assertEqual(self.store._enqueue.call_count, 1)
        with patch.object(self.store, "start_scheduler"):
            paused = self.store.submit("Research another topic", scheduled_at=future.isoformat())
        self.store.pause(paused["id"])
        self.store.dispatch_due(future + timedelta(seconds=2))
        self.assertEqual(self.store.get(paused["id"])["status"], "paused")

    def test_scheduling_requires_future_time_and_timezone(self):
        with self.assertRaises(ValueError):
            self.store.submit("Task", scheduled_at="2099-01-01T09:00:00")
        with self.assertRaises(ValueError):
            self.store.submit("Task", scheduled_at="2001-01-01T09:00:00+00:00")

    def test_distinct_image_count_and_aspect_ratio(self):
        path = self.root / "product.png"
        Image.new("RGB", (90, 160), "white").save(path)
        artifact = verify_artifact(path)
        job = {"goal": "Create 2 product images in 9:16", "workflow": "image"}
        step = {"output": "image", "instruction": "Create product images"}
        with self.assertRaises(QualityIssue):
            objective_checks(job, step, [artifact, artifact])
        job["goal"] = "Create 1 product image in 9:16"
        self.assertEqual(objective_checks(job, step, [artifact]), [artifact])
        job["goal"] = "Create 1 product image in 1:1"
        with self.assertRaises(QualityIssue):
            objective_checks(job, step, [artifact])

    def test_independent_review_must_not_invent_success(self):
        path = self.root / "report.md"
        path.write_text("Actual research findings with source references.")
        artifact = verify_artifact(path)
        job = {"goal": "Research competitors", "brand_context": {}, "workflow": "competitors"}
        step = {"output": "report", "instruction": "Research competitors"}
        with patch("core.gemini.as_json", return_value=None):
            result = review_delivery(job, step, [artifact])
        self.assertEqual(result["status"], "needs_review")
        with patch("core.gemini.as_json", return_value={"status": "passed", "checks": [{"name": "Facts", "status": "failed"}]}):
            result = review_delivery(job, step, [artifact])
        self.assertEqual(result["status"], "failed")

    def test_handoff_includes_actual_report_text_and_skips_rejected_files(self):
        accepted = self.root / "research.md"
        accepted.write_text("Verified product facts")
        rejected = self.root / "bad.md"
        rejected.write_text("Rejected invented claim")
        prompt = build_prompt({"goal": "Write copy", "brand_context": {}, "artifacts": [
            {"path": str(accepted)}, {"path": str(rejected), "rejected": True}]}, {"instruction": "Write copy"})
        self.assertIn("Verified product facts", prompt)
        self.assertNotIn("Rejected invented claim", prompt)


if __name__ == "__main__":
    unittest.main()
