"""Voice entrypoint for FRIDAY's persistent marketing coordinator."""
import json
from core.friday_workspace import get_workspace
from core.friday_services import CATALOG


def marketing_workspace(parameters, player=None):
    params = parameters or {}
    store = get_workspace()
    if player:
        store.notify = player.write_log
    action = params.get("action", "list")
    if action == "submit":
        files = params.get("files", [])
        if not files and player and player.current_file:
            files = [player.current_file]
        job = store.submit(params.get("goal", ""), params.get("workflow", "custom"),
            params.get("service", "Auto"), params.get("brand", ""), files,
            params.get("mode", "browser"), params.get("steps") or None, params.get("scheduled_at"))
        return json.dumps({"status": job["status"], "job_id": job["id"], "output": job["output"],
            "message": "Job queued, not completed. FRIDAY reports progress in the existing HUD and voice conversation. Ask for status, pause, resume or cancel by voice. The user may need to sign in. Do not claim that the final files already exist."})
    if action == "list":
        return json.dumps([{k: j[k] for k in ("id", "title", "status", "message")} for j in store.jobs()[:25]])
    if action == "status":
        return json.dumps(store.get(_job_id(store, params)))
    if action == "cancel":
        return json.dumps(store.cancel(_job_id(store, params)))
    if action == "pause":
        return json.dumps(store.pause(_job_id(store, params)))
    if action == "services":
        from core.friday_services import CATALOG
        return json.dumps({name: spec["skills"] for name,spec in CATALOG.items()})
    if action == "resume":
        return json.dumps(store.resume(_job_id(store, params)))
    if action == "brands":
        return json.dumps(store.brands())
    if action == "save_brand":
        store.save_brand(params.get("brand", ""), params.get("brand_profile", {}))
        return "Brand profile saved."
    return "Unknown workspace action."


def _job_id(store, params):
    """Natural voice commands refer to the current task without a job ID."""
    if params.get("job_id"):
        return params["job_id"]
    if store.active:
        return store.active
    jobs = store.jobs()
    if not jobs:
        raise ValueError("There is no job yet.")
    return jobs[0]["id"]


TOOL = {
    "name": "marketing_workspace",
    "description": "FRIDAY's central marketing/ecommerce coordinator. Queue browser or whole-desktop workflows that delegate to Gemini, ChatGPT, Claude, Canva or CapCut websites, with durable progress and verified downloads. Use for competitor research, campaigns, product listings, content, images, video, publishing preparation or performance CSV analysis. Automatically plan and choose services with service=Auto; save brand profiles; get status, pause, resume or cancel. Can schedule future tasks while FRIDAY is running and export actual reporting-account CSV data for local analytics. Submit queues background work and is NOT completion. No extra provider API keys; uses existing Gemini reasoning. Ask only for essential missing business facts. Protected actions accept the fresh phrase from actual user speech or the original HUD button. Submit, progress, resume and cancellation are voice-first; do not direct the user to a separate workspace. Omit job_id for the current or latest job.",
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "enum": ["submit", "list", "status", "pause", "cancel", "resume", "brands", "save_brand", "services"]},
        "goal": {"type": "STRING"},
        "scheduled_at": {"type": "STRING", "description": "Optional future ISO datetime with explicit timezone offset. Scheduled jobs run when FRIDAY is open; do not promise OS wake or unattended approval."},
        "workflow": {"type": "STRING", "enum": ["image", "video", "competitors", "campaign", "product_listing", "content", "publish", "custom", "analytics"]},
        "service": {"type": "STRING", "enum": ["Auto", *CATALOG]},
        "mode": {"type": "STRING", "enum": ["browser", "desktop"]},
        "brand": {"type": "STRING"},
        "job_id": {"type": "STRING"},
        "files": {"type": "ARRAY", "items": {"type": "STRING"}},
        "steps": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "service": {"type": "STRING", "enum": [*CATALOG, "Local"]},
            "instruction": {"type": "STRING"}, "output": {"type": "STRING", "enum": ["report", "image", "video", "csv", "publication"]},
            "executor": {"type": "STRING", "enum": ["browser", "analytics"]}, "mode": {"type": "STRING", "enum": ["browser", "desktop"]}}, "required": ["service", "instruction"]}},
        "brand_profile": {"type": "OBJECT", "properties": {k: {"type": "STRING"} for k in ["website", "audience", "offer", "voice", "facts", "language", "currency"]}},
    }, "required": ["action"]},
    "handler": marketing_workspace,
}
