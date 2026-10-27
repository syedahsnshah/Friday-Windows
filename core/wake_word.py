"""Local Friday detection. main.py supplies 16 kHz PCM; no extra microphone.

Vosk and its English speech model are installed only by the setup action.
"""
from __future__ import annotations
import importlib.util
import json
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import zipfile
from pathlib import Path

MODEL_DIR = Path(__file__).resolve().parent.parent / "memory" / "wake" / "vosk-model-small-en-us-0.15"
MODEL_URL = "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"
DEFAULT_THRESHOLD = 0.5
SAMPLE_RATE = 16000


def is_installed():
    return importlib.util.find_spec("vosk") is not None


def is_ready():
    return is_installed() and (MODEL_DIR / "am" / "final.mdl").is_file() and (MODEL_DIR / "conf" / "model.conf").is_file()


def install_and_download(logger=print, notify=None):
    tell = notify or logger
    try:
        if not is_installed():
            tell("Installing the local Friday wake recognizer…")
            result = subprocess.run([sys.executable, "-m", "pip", "install", "vosk>=0.3.44,<0.4"], capture_output=True, text=True, timeout=240)
            if result.returncode:
                return False, "Could not install Vosk. Check the connection and package installer."
        if not is_ready():
            tell("Downloading the local English wake model (about 40 MB)…")
            MODEL_DIR.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(dir=MODEL_DIR.parent) as directory:
                tmp = Path(directory)
                archive = tmp / "model.zip"
                with urllib.request.urlopen(MODEL_URL, timeout=120) as response, archive.open("wb") as stream:
                    shutil.copyfileobj(response, stream)
                with zipfile.ZipFile(archive) as z:
                    for item in z.infolist():
                        if not (tmp / item.filename).resolve().is_relative_to(tmp.resolve()):
                            raise ValueError("Invalid model archive path.")
                    z.extractall(tmp)
                extracted = tmp / MODEL_DIR.name
                if not (extracted / "am" / "final.mdl").is_file():
                    raise ValueError("Downloaded model is incomplete.")
                if MODEL_DIR.exists():
                    shutil.rmtree(MODEL_DIR)
                shutil.move(str(extracted), str(MODEL_DIR))
        return is_ready(), "Friday wake word is ready. Say Friday or Hey Friday."
    except Exception as exc:
        return False, f"Friday wake setup failed: {exc}"


class WakeWordDetector:
    def __init__(self, on_detect, threshold=DEFAULT_THRESHOLD, logger=print, notify=None):
        self._on_detect, self._logger = on_detect, logger
        self._notify = notify or logger
        self._queue = queue.Queue(maxsize=50)
        self._running = self._ready = False
        self._thread = None

    @property
    def ready(self):
        return self._ready

    def start(self):
        if self._running:
            return True
        if not is_ready():
            self._notify("Friday wake model is not installed. Use Wake Word Download or Wake Now.")
            return False
        try:
            from vosk import Model, KaldiRecognizer
            self._model = Model(str(MODEL_DIR))
            self._recognizer = KaldiRecognizer(self._model, SAMPLE_RATE, json.dumps(["friday", "hey friday", "[unk]"]))
            self._running = self._ready = True
            self._thread = threading.Thread(target=self._loop, daemon=True, name="FridayWake")
            self._thread.start()
            self._logger("Listening locally for Friday / Hey Friday.")
            return True
        except Exception as exc:
            self._notify(f"Friday wake unavailable: {exc}")
            return False

    def stop(self):
        self._running = self._ready = False
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=2)

    def feed(self, frame_int16):
        if self._running:
            try:
                self._queue.put_nowait(frame_int16.copy().tobytes())
            except queue.Full:
                pass

    def _loop(self):
        last_detection = 0.0
        while self._running:
            try:
                data = self._queue.get(timeout=0.5)
                if data is None:
                    break
                final = self._recognizer.AcceptWaveform(data)
                result = json.loads(self._recognizer.Result() if final else self._recognizer.PartialResult())
                text = result.get("text", result.get("partial", "")).lower().split()
                if "friday" in text and time.monotonic() - last_detection > 3:
                    last_detection = time.monotonic()
                    self._recognizer.Reset()
                    self._on_detect()
            except queue.Empty:
                continue
            except Exception as exc:
                self._logger(f"Friday wake error: {exc}")
