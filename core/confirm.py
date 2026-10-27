"""Human confirmation for a specific action, through the original FRIDAY HUD.

A button or an exact, fresh spoken phrase can approve. Spoken input is accepted
only from the main audio-input transcription path, never from model-written
tool parameters or another AI's response. Phrases expire and are consumed once.
The protected operation runs off the Qt/audio thread. Reversible operations
continue to use the existing undo mechanism.
"""

from __future__ import annotations

import threading
import time
import re
import secrets
from dataclasses import dataclass
from typing import Callable, Optional

# A pending confirmation is abandoned after this long. Chosen to outlast a
# normal "hang on, let me look at the screen" pause without leaving a live
# shutdown button sitting on the HUD for the rest of the day.
TIMEOUT_SECONDS = 90.0


@dataclass
class _Pending:
    key:     str
    title:   str
    detail:  str
    run:     Callable[[], str]
    at:      float
    phrase:  str
    on_cancel: Optional[Callable[[], None]] = None


_pending: Optional[_Pending] = None
_lock = threading.Lock()

# Set once at startup by main.py. Signature: (title, detail) -> None for show,
# and () -> None for hide. Both are marshalled onto the Qt thread by the UI.
_show_cb: Optional[Callable[[str, str], None]] = None
_hide_cb: Optional[Callable[[], None]] = None
_log_cb:  Optional[Callable[[str], None]] = None


def bind(show, hide, log=None) -> None:
    """Wire this module to the HUD. Called once from main.py at startup."""
    global _show_cb, _hide_cb, _log_cb
    _show_cb, _hide_cb, _log_cb = show, hide, log


def _log(msg: str) -> None:
    if _log_cb:
        try:
            _log_cb(msg)
        except Exception:
            pass


def request(key: str, title: str, detail: str, run: Callable[[], str], on_cancel=None) -> str:
    """Park an irreversible action behind the on-screen gate.

    Returns the sentence the tool should hand back to the model — phrased as an
    instruction so the assistant asks the user out loud in their own language,
    rather than reading an English string verbatim."""
    global _pending

    if _show_cb is None:
        # No interface bound (headless, or a very early call). Refuse rather
        # than silently performing something irreversible.
        return (f"I cannot confirm '{title}' right now because the interface is "
                f"not available, so I have not done it.")

    words = ("amber", "river", "silver", "maple", "ocean", "cedar", "violet", "meadow")
    phrase = " ".join(secrets.choice(words) for _ in range(2))
    voice_help = f"Say 'Friday confirm {phrase}' to approve, or 'Friday cancel action' to cancel."
    with _lock:
        _pending = _Pending(key=key, title=title, detail=detail,
                            run=run, at=time.monotonic(), phrase=phrase, on_cancel=on_cancel)

    try:
        _show_cb(title, detail + "\n" + voice_help)
    except Exception as e:
        with _lock:
            _pending = None
        return f"Could not ask for confirmation: {e}. Nothing was done."

    _log(f"SYS: Awaiting confirmation — {title}")
    return (
        f"[CONFIRMATION_PENDING] I have put a confirmation on screen for: {title}. "
        f"Explain the concrete action and tell the user: {voice_help} "
        f"Only the actual input-audio transcript or the HUD button can approve it. "
        f"Do not claim it is done."
    )


def resolve(accepted: bool) -> None:
    """Called by the UI when the user presses CONFIRM or CANCEL.

    Runs the stored callable on a worker thread — this is invoked from the Qt
    thread, and shutting the machine down from inside a button handler would
    freeze the interface on its way out."""
    global _pending

    with _lock:
        p, _pending = _pending, None

    if _hide_cb:
        try:
            _hide_cb()
        except Exception:
            pass

    if p is None:
        return

    if time.monotonic() - p.at > TIMEOUT_SECONDS:
        _log(f"SYS: Confirmation expired — {p.title}")
        return

    if not accepted:
        _log(f"SYS: Cancelled — {p.title}")
        if p.on_cancel:
            threading.Thread(target=p.on_cancel, daemon=True, name="confirm-cancel").start()
        return

    def _worker():
        try:
            result = p.run() or "Done."
            _log(f"SYS: Confirmed — {p.title}. {result}")
        except Exception as e:
            _log(f"ERR: {p.title} failed — {e}")

    threading.Thread(target=_worker, daemon=True,
                     name=f"confirm-{p.key}").start()


def resolve_spoken_input(transcript: str) -> bool:
    """Called only for genuine input-audio transcription, never tool arguments.

    An exact, fresh, per-action phrase prevents a generated 'confirmed=true'
    tool argument or a casual yes from approving its own action.
    """
    normalized = re.sub(r"[^a-z ]", " ", transcript.lower())
    normalized = " ".join(normalized.split())
    if normalized.startswith("friday "):
        normalized = normalized[7:]
    with _lock:
        p = _pending
        if p is None or time.monotonic() - p.at > TIMEOUT_SECONDS:
            return False
        approve = normalized == "confirm " + p.phrase
        cancel = normalized == "cancel action"
        if not approve and not cancel:
            return False
    return _resolve_spoken_request(p, approve)


def _resolve_spoken_request(expected, accepted):
    global _pending
    with _lock:
        if _pending is not expected or time.monotonic() - expected.at > TIMEOUT_SECONDS:
            return False
        # resolve() takes the same lock; reserve this action by detaching it.
        _pending = None
    if _hide_cb:
        try:
            _hide_cb()
        except Exception:
            pass
    if not accepted:
        if expected.on_cancel:
            threading.Thread(target=expected.on_cancel, daemon=True).start()
        _log(f"SYS: Cancelled by voice — {expected.title}")
    else:
        def run():
            try:
                result = expected.run() or "Done."
                _log(f"SYS: Confirmed by voice — {expected.title}. {result}")
            except Exception as exc:
                _log(f"ERR: {expected.title} failed — {exc}")
        threading.Thread(target=run, daemon=True, name="voice-confirm").start()
    return True


def voice_instruction():
    with _lock:
        if _pending is None or time.monotonic() - _pending.at > TIMEOUT_SECONDS:
            return ""
        return f"Say Friday confirm {_pending.phrase} to approve, or Friday cancel action to cancel."


def pending_title() -> str:
    """'' when nothing is waiting. Lets an action avoid stacking two banners."""
    with _lock:
        if _pending is None:
            return ""
        if time.monotonic() - _pending.at > TIMEOUT_SECONDS:
            return ""
        return _pending.title
