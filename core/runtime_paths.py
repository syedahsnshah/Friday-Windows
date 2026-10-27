"""Application files selected by the packaged launcher, without changing source runs."""
from pathlib import Path
import os
import sys


def application_root() -> Path:
    runtime = os.environ.get('FRIDAY_RUNTIME_DIR')
    if runtime:
        return Path(runtime).expanduser().resolve()
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent
