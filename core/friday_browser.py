"""Reuse a running macOS browser and its active tab. Never launches a browser.

AppleScript JavaScript access is optional. Without it the operator uses the
existing screenshot/mouse/keyboard path, preserving the same signed-in session.
"""
from __future__ import annotations
import json
import subprocess
import sys
import time
from pathlib import Path

BROWSERS = {"chrome": "Google Chrome", "edge": "Microsoft Edge", "brave": "Brave Browser", "safari": "Safari", "vivaldi": "Vivaldi", "opera": "Opera"}


def running_browsers():
    if sys.platform != "darwin":
        return []
    return [name for name, app in BROWSERS.items() if subprocess.run(["pgrep", "-x", app], capture_output=True).returncode == 0]


def _script(script):
    result = subprocess.run(["osascript", "-"], input=script, text=True, capture_output=True, timeout=15)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "Existing browser could not be controlled.")
    return result.stdout.strip()


def preferences_path():
    from core.friday_workspace import ROOT
    return ROOT / "memory" / "browser-preference.json"


def select_browser(preferred=None):
    available = running_browsers()
    saved = None
    try:
        saved = json.loads(preferences_path().read_text()).get("browser")
    except (OSError, ValueError):
        pass
    choice = (preferred or saved or "").lower().strip()
    if choice in BROWSERS and choice in available:
        return choice
    if preferred:
        raise RuntimeError(f"{preferred} is not an already running supported browser. FRIDAY will not open a new browser.")
    if len(available) == 1:
        return available[0]
    if not available:
        raise RuntimeError("No supported existing browser is running. Open your usual signed-in browser yourself, then say resume.")
    raise RuntimeError("Which existing browser should FRIDAY use? Say use " + ", or use ".join(available) + ", then resume.")


def remember_browser(name):
    name = select_browser(name)
    path = preferences_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"browser": name}))
    return name


class ExistingPage:
    native = True
    def __init__(self, name):
        self.name, self.app = name, BROWSERS[name]
        # Check a window exists BEFORE activation: activation must not create one.
        if int(self.script("count windows") or 0) < 1:
            raise RuntimeError(f"{self.app} has no existing window. Open one yourself, then resume.")
        self.dom = False
        try:
            self.evaluate("() => location.href")
            self.dom = True
        except RuntimeError:
            pass

    def script(self, body):
        if self.name not in running_browsers():
            raise RuntimeError("The selected browser has closed. FRIDAY will not relaunch it.")
        return _script(f'tell application {json.dumps(self.app)}\n{body}\nend tell')

    def evaluate(self, expression):
        code = f"JSON.stringify(({expression})())"
        target = "current tab of front window" if self.name == "safari" else "active tab of front window"
        verb = f"do JavaScript {json.dumps(code, ensure_ascii=False)} in {target}" if self.name == "safari" else f"execute {target} javascript {json.dumps(code, ensure_ascii=False)}"
        raw = self.script(verb)
        return json.loads(raw) if raw else None

    @property
    def url(self):
        target = "current tab" if self.name == "safari" else "active tab"
        return self.script(f"get URL of {target} of front window")

    def goto(self, url, **kwargs):
        target = "current tab" if self.name == "safari" else "active tab"
        self.script(f"set URL of {target} of front window to {json.dumps(url, ensure_ascii=False)}\nactivate")

    def title(self):
        return self.evaluate("() => document.title") if self.dom else self.app

    def screenshot(self, **kwargs):
        from core.friday_operator import desktop_observation
        self.script("activate")
        return desktop_observation()[0]

    def locator(self, selector):
        return ExistingLocator(self, selector)

    def wait_for_timeout(self, milliseconds):
        time.sleep(milliseconds / 1000)

    def is_closed(self):
        return self.name not in running_browsers()

    def on(self, *args):
        pass


class ExistingLocator:
    def __init__(self, page, selector):
        self.page, self.selector = page, selector

    def query(self, body):
        return self.page.evaluate(f"() => {{let es=Array.from(document.querySelectorAll({json.dumps(self.selector)})); return {body};}}")

    def element_handles(self):
        return [ExistingHandle(self, i) for i in range(self.query("es.length"))]

    def inner_text(self, **kwargs):
        return self.query("es[0]?.innerText || ''")

    def all_text_contents(self):
        return self.query("es.map(e=>e.textContent)")

    def evaluate_all(self, function):
        return self.query(f"({function})(es)")


class ExistingHandle:
    def __init__(self, locator, index):
        self.locator, self.index = locator, index

    def evaluate(self, function):
        return self.locator.query(f"({function})(es[{self.index}])")

    def is_visible(self):
        return self.evaluate("e => !!(e && e.getClientRects().length && getComputedStyle(e).visibility!=='hidden')")

    def get_attribute(self, name):
        return self.evaluate(f"e=>e.getAttribute({json.dumps(name)})")

    def click(self):
        return self.evaluate("e=>{if(!e||e.disabled)throw Error('Control unavailable');e.click();return true;}")

    def fill(self, text):
        return self.evaluate("e=>{if(e.type==='password')throw Error('User must enter passwords');e.focus();" +
            f"let t={json.dumps(text)};" + "if(e.isContentEditable){e.textContent=t;}else{let p=e.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;Object.getOwnPropertyDescriptor(p,'value').set.call(e,t);}e.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertText',data:t}));e.dispatchEvent(new Event('change',{bubbles:true}));return true;}")

    def set_input_files(self, files):
        raise ValueError("Use the existing browser's visible attachment button and native file dialog; websites cannot set file inputs through JavaScript.")


class ExistingContext:
    def __init__(self, name=None):
        self.pages = [ExistingPage(select_browser(name))]

    def set_default_timeout(self, value):
        pass

    def on(self, *args):
        pass

    def new_page(self):
        raise RuntimeError("FRIDAY reuses existing tabs and will not create a new browser or tab.")

    def close(self):
        # Ownership remains with the user. Never close their browser on exit.
        pass


def open_existing_context():
    return ExistingContext()
