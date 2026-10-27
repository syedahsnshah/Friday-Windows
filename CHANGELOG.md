# FRIDAY 56.0.0 — original HUD, voice workflows, existing browsers

- Preserve the original interface and voice-first computer control.
- Reuse a running browser's active tab and signed-in session; never launch a new browser, profile, window or tab. Remember a browser selected by voice. Ask when the choice is ambiguous. Leave the user's browser open afterward.
- Use observed browser controls where browser scripting is enabled; otherwise use screenshot, mouse, keyboard and native file dialogs. OS permissions remain controlled by macOS.
- Plan bounded multi-service jobs, carry actual reports/files between stages, persist checkpoints, pause/resume/cancel by voice, journal AI prompt submissions, and recover from transient failures.
- Check real downloaded media and review contents against the brief. Surface incomplete/unverified results for review. Never automatically retry an unverified publication.
- Support brand profiles, ecommerce campaign/listing/research workflows, reporting CSV exports and local metrics, and future jobs while FRIDAY is running.
- Keep application ownership notices as techobux and preserve third-party notices.

Validation: automated regression checks and packaged HUD/tool smoke test. Earlier synthetic speech reached the real voice tool route. Signed-in service generation, publishing and native browser permission dialogs need the user's account tests; no successful live media generation is claimed.

# FRIDAY 55.0.2 — original interface, spoken operation

- Remove the standalone marketing screen from the source and package.
- Preserve the original FRIDAY HUD and its existing controls.
- Add fresh per-action spoken confirmations from real input-audio transcription;
  model-generated tool parameters cannot approve their own actions.
- Keep marketing task submission, progress, resume and cancellation in voice.

# FRIDAY 55.0.1 — voice-first correction

- Restore the original HUD layout; remove the new workspace button and standalone launch mode.
- Keep new marketing and ecommerce capabilities behind spoken commands.
- Resolve status, resume and cancel requests against the current/latest job automatically.
- Use the original HUD confirmation banner for protected external actions.
- Preserve completed-job notifications until FRIDAY is awake to report them.

# FRIDAY 55.0.0 — 24 October 2026

- Rebrand application UI, voice identity, dashboard and packaging as FRIDAY.
- Set application ownership notices to techobux; preserve third-party terms.
- Add Marketing Workspace, brand profiles and durable multi-service workflow jobs.
- Add browser/desktop visual execution, file handoffs, downloads and media checks.
- Add ecommerce campaign, listing, competitor and content workflow briefs.
- Add deterministic marketing CSV reporting and saved delivery manifests.
- Add action review, cancellation, pause/resume and restart recovery.
- Replace the former wake detector with a Friday-specific local Vosk recognizer.
- Extend packaged smoke checks to the workspace and the additional voice tool.

Live third-party AI workflows require signed-in accounts and validation with
those services. Generic visual automation is not a certified integration.
