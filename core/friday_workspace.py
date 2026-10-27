"""FRIDAY's durable marketing workspace. No network or desktop effects on import."""
from __future__ import annotations

import csv
import hashlib
import json
import math
import queue
import re
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from core.friday_services import CATALOG, basic_plan, infer_workflow, validate_plan

ROOT = Path(__file__).resolve().parent.parent
SERVICES = {name: spec["url"] for name, spec in CATALOG.items()}
WORKFLOWS = {
    "image": "Create the requested image and download the actual image file.",
    "video": "Edit the supplied video according to the brief and export the actual edited video.",
    "competitors": "Research public competitor websites. Compare offers, prices, positioning, audiences and claims. Include source URLs and observation dates; distinguish facts from inference. Produce a sourced report.",
    "campaign": "Create an ecommerce campaign: audience and offer, sourced competitor observations, three distinct campaign angles, ad copy, product image briefs, video script, calls to action and a seven-day content plan. Never invent product benefits, testimonials, prices or research. Save the campaign report and requested assets.",
    "product_listing": "Prepare an ecommerce product listing: title, benefits grounded in provided facts, description, FAQ, SEO terms, image briefs and missing information. Save a report. Do not publish unless explicitly authorized.",
    "content": "Create the requested marketing content in the brand voice, with clear calls to action. Save the final copy and requested media.",
    "publish": "Prepare the requested scheduling or publishing task. Publishing, sending to people and spending require approval of the concrete final action in FRIDAY. Do not treat a draft as published.",
    "custom": "Carry out the user's requested workflow and save the final deliverables.",
}


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def verify_artifact(path):
    """Reject partial/empty downloads; identify common media by decoding them."""
    p = Path(path)
    if not p.is_file() or p.is_symlink() or p.stat().st_size == 0:
        raise ValueError("The output is missing, empty or a symbolic link.")
    if p.suffix.lower() in {".part", ".crdownload", ".tmp"}:
        raise ValueError("The download is incomplete.")
    result = {"path": str(p.resolve()), "bytes": p.stat().st_size, "verified_at": now()}
    digest = hashlib.sha256()
    with p.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(block)
    result["sha256"] = digest.hexdigest()
    if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
        from PIL import Image
        with Image.open(p) as im:
            result["dimensions"] = list(im.size)
            im.verify()
        result["check"] = "Image decoded; size and checksum verified. Creative quality needs review."
    elif p.suffix.lower() in {".mp4", ".mov", ".webm", ".mkv"}:
        import cv2
        cap = cv2.VideoCapture(str(p))
        try:
            ok, frame = cap.read()
            if not ok:
                raise ValueError("The exported video could not be decoded.")
            result["dimensions"] = [int(cap.get(3)), int(cap.get(4))]
            fps = cap.get(cv2.CAP_PROP_FPS)
            result["duration_seconds"] = cap.get(cv2.CAP_PROP_FRAME_COUNT) / fps if fps else None
        finally:
            cap.release()
        result["check"] = "Video frame decoded; size and checksum verified. Edit and audio need review."
    else:
        result["check"] = "Non-empty file and checksum verified; contents need review."
    return result


def check_media_brief(job):
    """Enforce objectively measurable requirements stated explicitly in a brief."""
    if job["workflow"] not in {"image", "video"}:
        return
    dims = re.search(r"\b(\d{2,5})\s*[x×]\s*(\d{2,5})\b", job["goal"])
    duration = re.search(r"\b(\d+(?:\.\d+)?)\s*[- ]?\s*(?:second|sec)s?\b", job["goal"], re.I)
    types = {"image": {".png", ".jpg", ".jpeg", ".webp"}, "video": {".mp4", ".mov", ".webm", ".mkv"}}
    media = [a for a in job["artifacts"] if Path(a["path"]).suffix.lower() in types[job["workflow"]]]
    if not media:
        raise ValueError("The requested media output is missing.")
    if dims and not any(a.get("dimensions") == [int(dims[1]), int(dims[2])] for a in media):
        raise ValueError(f"The export does not match the requested {dims[1]} × {dims[2]} dimensions.")
    if duration and job["workflow"] == "video":
        seconds = float(duration[1])
        if not any(a.get("duration_seconds") is not None and abs(a["duration_seconds"] - seconds) <= max(1, seconds * .05) for a in media):
            raise ValueError("The exported video duration does not match the requested duration (within 5% or one second).")


def analyze_csv(path, output):
    """Aggregate exported marketing data without inventing missing metrics."""
    totals, present, count = {}, set(), 0
    fields = {"spend", "impressions", "clicks", "leads", "orders", "revenue"}
    with Path(path).open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError("CSV needs a header row.")
        names = {x: x.strip().lower().replace(" ", "_") for x in reader.fieldnames}
        present = fields.intersection(names.values())
        if not present:
            raise ValueError("Use columns: spend, impressions, clicks, leads, orders, revenue.")
        totals = {x: 0.0 for x in present}
        for row in reader:
            if not any(str(v or "").strip() for v in row.values()):
                continue
            count += 1
            for key, normalized in names.items():
                if normalized not in present:
                    continue
                raw = str(row.get(key) or "").strip().replace(",", "")
                if not raw:
                    raise ValueError(f"Missing {normalized} in data row {count}; blank is not zero.")
                value = float(raw)
                if not math.isfinite(value) or value < 0:
                    raise ValueError(f"Invalid {normalized} in data row {count}.")
                totals[normalized] += value
    if not count:
        raise ValueError("CSV has no data rows.")
    def ratio(a, b, factor=1):
        return totals[a] / totals[b] * factor if a in totals and totals.get(b, 0) > 0 else None
    metrics = {"CTR (%)": ratio("clicks", "impressions", 100), "CPC": ratio("spend", "clicks"),
               "CPL": ratio("spend", "leads"), "Cost per order": ratio("spend", "orders"),
               "ROAS": ratio("revenue", "spend"), "Order conversion (%)": ratio("orders", "clicks", 100)}
    report = {"source": str(Path(path).resolve()), "rows": count, "created_at": now(), "totals": totals,
              "metrics": metrics, "note": "All amounts must use one currency. Revenue is not profit. Missing metrics are unavailable; attribution and tracking were not independently verified."}
    out = Path(output)
    out.mkdir(parents=True, exist_ok=True)
    (out / "performance.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = ["# FRIDAY — marketing performance", "", f"Rows analyzed: {count}", "", "## Totals", ""]
    lines += [f"- {k}: {v:,.2f}" for k, v in totals.items()]
    lines += ["", "## Metrics", ""] + [f"- {k}: {v:,.2f}" if v is not None else f"- {k}: unavailable" for k, v in metrics.items()]
    lines += ["", report["note"], "", "Compare against your own baseline and check tracking before changing spend."]
    (out / "performance.md").write_text("\n".join(lines), encoding="utf-8")
    return [verify_artifact(out / "performance.json"), verify_artifact(out / "performance.md")]


class Workspace:
    def __init__(self, root=ROOT, output_root=None):
        self.root = Path(root)
        self.state = self.root / "memory" / "friday"
        self.state.mkdir(parents=True, exist_ok=True)
        self.outputs = Path(output_root) if output_root else Path.home() / "Downloads" / "FRIDAY"
        self.db = self.state / "workspace.sqlite3"
        self.queue = queue.Queue()
        self.lock = threading.RLock()
        self.worker = None
        self.active = None
        self.notify = None
        self._approvals = set()
        self.scheduler = None
        self.scheduler_stop = threading.Event()
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, data TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS brands (name TEXT PRIMARY KEY, data TEXT NOT NULL)")
            for ident, raw in db.execute("SELECT id,data FROM jobs").fetchall():
                job = json.loads(raw)
                if job["status"] in {"queued", "running", "waiting_user"}:
                    job.update(status="paused", pending_action=None, message="App restarted. Say resume to continue from the saved checkpoint.", updated_at=now())
                    db.execute("UPDATE jobs SET data=? WHERE id=?", (json.dumps(job), ident))

    def connect(self):
        return sqlite3.connect(self.db, timeout=15)

    def get(self, ident):
        with self.connect() as db:
            row = db.execute("SELECT data FROM jobs WHERE id=?", (ident,)).fetchone()
        if not row:
            raise ValueError("Job not found.")
        return json.loads(row[0])

    def jobs(self):
        with self.connect() as db:
            return sorted([json.loads(r[0]) for r in db.execute("SELECT data FROM jobs")], key=lambda j: j["created_at"], reverse=True)

    def update(self, ident, **changes):
        with self.lock, self.connect() as db:
            raw = db.execute("SELECT data FROM jobs WHERE id=?", (ident,)).fetchone()
            if not raw:
                raise ValueError("Job not found.")
            job = json.loads(raw[0])
            if job["status"] == "cancelled" and changes.get("status") != "cancelled":
                return job
            if job["status"] == "paused" and changes.get("status") in {"running", "waiting_user", "completed", "needs_review", "failed"}:
                return job
            job.update(changes, updated_at=now())
            db.execute("UPDATE jobs SET data=? WHERE id=?", (json.dumps(job), ident))
        if self.notify and "message" in changes:
            self.notify(f"FRIDAY: {job['title']} — {job['message']}")
        return job

    def brands(self):
        with self.connect() as db:
            return {name: json.loads(raw) for name, raw in db.execute("SELECT name,data FROM brands")}

    def save_brand(self, name, data):
        if not name.strip():
            raise ValueError("A brand name is required.")
        allowed = {"audience", "offer", "voice", "facts", "website", "language", "currency"}
        clean = {k: str(v)[:12000] for k, v in data.items() if k in allowed}
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO brands VALUES (?,?)", (name.strip(), json.dumps(clean)))

    def submit(self, goal, workflow="custom", service="Gemini", brand="", files=None, mode="browser", steps=None, scheduled_at=None):
        if not goal.strip():
            raise ValueError("Describe the outcome you want.")
        if workflow not in {*WORKFLOWS, "analytics"} or service not in {*SERVICES, "Auto"} or mode not in {"browser", "desktop"}:
            raise ValueError("Unknown workflow, AI service or control mode.")
        attachments = []
        for value in files or []:
            p = Path(value).expanduser().resolve()
            if not p.is_file():
                raise ValueError(f"Attachment does not exist: {p.name}")
            attachments.append(str(p))
        if workflow == "custom":
            workflow = infer_workflow(goal, attachments)
        if workflow == "analytics" and attachments and not any(p.lower().endswith(".csv") for p in attachments):
            raise ValueError("Attach an actual CSV export, or ask FRIDAY to export data from the reporting account.")
        import copy
        raw_plan = copy.deepcopy(steps) if steps else basic_plan(workflow, goal, service, attachments)
        if steps:
            for index, step in enumerate(raw_plan):
                # Keep older callers compatible while allowing mixed report/media plans.
                step.setdefault("output", workflow if index == len(raw_plan)-1 and workflow in {"image", "video"} else "report")
        plan = validate_plan(raw_plan, mode)
        scheduled = None
        if scheduled_at:
            target = datetime.fromisoformat(str(scheduled_at).replace("Z", "+00:00"))
            if target.tzinfo is None:
                raise ValueError("Scheduled time needs an explicit timezone offset.")
            if target <= datetime.now(timezone.utc):
                raise ValueError("Scheduled time must be in the future.")
            scheduled = target.astimezone(timezone.utc).isoformat()
        ident = uuid.uuid4().hex[:12]
        job = {"id": ident, "title": goal.strip()[:100], "goal": goal.strip(), "workflow": workflow,
               "brand": brand, "brand_context": self.brands().get(brand, {}), "steps": plan,
               "files": attachments, "output": str(self.outputs / ident), "status": "scheduled" if scheduled else "queued",
               "created_at": now(), "updated_at": now(), "step": 0, "actions": [], "artifacts": [],
               "message": "Scheduled; FRIDAY must be running at the due time." if scheduled else "Queued", "pending_action": None,
               "auto_plan": not bool(steps), "planned": bool(steps), "mode": mode,
               "preferred_service": service, "scheduled_at": scheduled, "checkpoint": {},
               "receipts": {}, "reviews": [], "recovery": [], "step_attempts": {}}
        with self.connect() as db:
            db.execute("INSERT INTO jobs VALUES (?,?)", (ident, json.dumps(job)))
        if scheduled:
            self.start_scheduler()
        else:
            self._enqueue(ident)
        return self.get(ident)

    def _enqueue(self, ident):
        with self.lock:
            self.queue.put(ident)
            if self.worker is None or not self.worker.is_alive():
                self.worker = threading.Thread(target=self._work, daemon=True, name="FridayCoordinator")
                self.worker.start()

    def cancel(self, ident):
        if self.get(ident)["status"] in {"completed", "cancelled"}:
            raise ValueError("This job has already finished.")
        return self.update(ident, status="cancelled", message="Cancelled by user.", pending_action=None)

    def pause(self, ident):
        job = self.get(ident)
        if job["status"] not in {"running", "queued", "waiting_user", "scheduled"}:
            raise ValueError("This task is not active.")
        return self.update(ident, status="paused", message="Paused by voice. Say resume to continue from the saved checkpoint.", pending_action=None)

    def resume(self, ident, approved=False):
        with self.lock:
            job = self.get(ident)
            if job["status"] not in {"waiting_user", "paused", "failed", "needs_review"}:
                raise ValueError("This job is not waiting or paused.")
            if job["status"] == "needs_review":
                attempts = dict(job.get("step_attempts", {}))
                attempts[str(job["step"])] = 0
                self.update(ident, step_attempts=attempts, review_only=job["step"] >= len(job["steps"]))
            if job.get("pending_action"):
                if not approved:
                    raise ValueError("Approve the concrete action on the FRIDAY HUD first.")
                self._approvals.add((ident, job["pending_action"]["token"]))
            status = "running" if self.active == ident and job["status"] == "waiting_user" else "queued"
            result = self.update(ident, status=status, message="Resuming after user review.")
            if status == "queued":
                self._enqueue(ident)
            return result

    def wait_for_user(self, ident, message, action=None):
        import time
        if self.get(ident)["status"] != "running":
            return False
        pending = None
        if action:
            token = hashlib.sha256(json.dumps(action, sort_keys=True).encode()).hexdigest()
            pending = {"token": token, "action": action}
        if self.update(ident, status="waiting_user", message=message, pending_action=pending)["status"] != "waiting_user":
            return False
        if action:
            # Reuse the original HUD's human-operated confirmation banner.
            # Voice and model tool arguments cannot approve their own action.
            from core import confirm
            confirm.request(
                "friday-job-" + ident, "Approve FRIDAY's next action", message,
                lambda: self._approve_from_hud(ident),
                on_cancel=lambda: self.cancel(ident))
            hint = confirm.voice_instruction()
            if hint:
                self.update(ident, message=message + " " + hint)
        deadline = time.monotonic() + 900
        while time.monotonic() < deadline:
            job = self.get(ident)
            if job["status"] in {"cancelled", "paused", "queued"}:
                return False
            if job["status"] == "running":
                if pending and (ident, pending["token"]) not in self._approvals:
                    return False
                self._approvals.discard((ident, pending["token"])) if pending else None
                self.update(ident, pending_action=None)
                return True
            time.sleep(0.3)
        self.update(ident, status="paused", message="Waiting timed out. Resume when ready.", pending_action=None)
        return False

    def _approve_from_hud(self, ident):
        self.resume(ident, approved=True)
        return "Approved action resumed."

    def start_scheduler(self):
        with self.lock:
            if self.scheduler is None or not self.scheduler.is_alive():
                self.scheduler_stop.clear()
                self.scheduler = threading.Thread(target=self._schedule_loop, daemon=True, name="FridaySchedules")
                self.scheduler.start()

    def _schedule_loop(self):
        while not self.scheduler_stop.wait(1):
            try:
                self.dispatch_due()
            except (sqlite3.Error, ValueError):
                # Preserve schedules through transient storage errors; retry next tick.
                continue

    def dispatch_due(self, current=None):
        current = current or datetime.now(timezone.utc)
        for job in self.jobs():
            if job["status"] == "scheduled" and datetime.fromisoformat(job["scheduled_at"]) <= current:
                updated = self.update(job["id"], status="queued", message="Scheduled time reached. Preparing task.")
                if updated["status"] == "queued":
                    self._enqueue(job["id"])

    def _work(self):
        while True:
            try:
                ident = self.queue.get(timeout=1)
            except queue.Empty:
                with self.lock:
                    if self.queue.empty():
                        self.worker = None
                        return
                continue
            self.active = ident
            try:
                job = self.get(ident)
                if job["status"] != "queued":
                    continue
                Path(job["output"]).mkdir(parents=True, exist_ok=True)
                self.update(ident, status="running", message="Preparing workflow.")
                if not job.get("planned"):
                    from core.friday_services import plan_job
                    plan = plan_job(job)
                    self.update(ident, steps=plan, planned=True, message="Task plan saved; starting the selected service.")
                    job = self.get(ident)
                if job["status"] != "running":
                    continue
                if job.get("review_only"):
                    from core.friday_quality import review_delivery
                    review = review_delivery(job, job["steps"][-1], job["artifacts"])
                    review.update(step=len(job["steps"])-1, reviewed_at=now())
                    self.update(ident, reviews=job.get("reviews", [])+[review], review_only=False)
                elif job["workflow"] == "analytics" and len(job["steps"]) == 1 and job["files"]:
                    csv = next(p for p in job["files"] if p.lower().endswith(".csv"))
                    artifacts = analyze_csv(csv, job["output"])
                    self.update(ident, artifacts=artifacts)
                else:
                    from core.friday_operator import run_job
                    if not run_job(self, ident):
                        continue
                job = self.get(ident)
                if job["status"] in {"cancelled", "paused", "queued", "waiting_user"}:
                    continue
                if not job["artifacts"]:
                    raise ValueError("No verified deliverable was produced.")
                check_media_brief(job)
                manifest = Path(job["output"]) / "delivery.json"
                latest_reviews = {r.get("step", i): r for i,r in enumerate(job.get("reviews", []))}
                review_pending = any(r.get("status") != "passed" for r in latest_reviews.values())
                manifest.write_text(json.dumps({"goal": job["goal"], "brand": job["brand"], "created_at": now(), "artifacts": job["artifacts"], "reviews": job.get("reviews", []), "quality": "Independent review requires attention." if review_pending else "Configured file and review checks passed; this is not a guarantee of factual accuracy, rights or marketing results."}, indent=2), encoding="utf-8")
                self.update(ident, status="needs_review" if review_pending else "completed", message="Files saved; the review found criteria that need your attention." if review_pending else "Deliverables saved and checked. Task complete.")
            except Exception as exc:
                if self.get(ident)["status"] not in {"paused", "cancelled", "queued"}:
                    self.update(ident, status="failed", message=str(exc)[:1000])
            finally:
                self.active = None
                self.queue.task_done()


_workspace = None
_workspace_lock = threading.Lock()


def get_workspace():
    global _workspace
    with _workspace_lock:
        if _workspace is None:
            _workspace = Workspace()
            _workspace.start_scheduler()
        return _workspace
