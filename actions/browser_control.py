"""Voice control of an existing signed-in browser; no browser launches."""
from __future__ import annotations

def _normalize_url(url: str) -> str:
    """
    Bare words like "instagram" → "https://instagram.com"
    Domains like "instagram.com" → "https://instagram.com"
    Full URLs pass through unchanged.
    """
    url = url.strip()
    if not url:
        return "about:blank"
    if "://" in url:
        return url
    # No dot at all → assume .com  (e.g. "instagram" → "instagram.com")
    if "." not in url:
        url = url + ".com"
    return "https://" + url


_SEARCH_ENGINES: dict[str, str] = {
    "google":     "https://www.google.com/search?q=",
    "bing":       "https://www.bing.com/search?q=",
    "duckduckgo": "https://duckduckgo.com/?q=",
    "yandex":     "https://yandex.com/search/?text=",
}

def browser_control(
    parameters:    dict = None,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    # All voice browser actions reuse a running application and active tab.
    # The legacy launch registry is deliberately unreachable from this entrypoint.
    from core.friday_browser import ExistingContext, running_browsers, remember_browser
    from core.friday_operator import desktop_action, safe_url
    import json
    from urllib.parse import quote_plus
    params = parameters or {}
    action = str(params.get("action", "")).lower().strip()
    browser = str(params.get("browser", "")).lower().strip() or None
    try:
        if action == "list_browsers":
            result = json.dumps({"running": running_browsers(), "policy": "Reuse existing windows and signed-in sessions only."})
        elif action == "switch":
            result = "Using your existing " + remember_browser(browser or params.get("target", "")) + " session. Say resume to continue a paused job."
        elif action in {"new_tab", "close", "close_all"}:
            result = "FRIDAY preserves your existing browser windows and tabs. Use go_to to navigate the active tab."
        else:
            if browser:
                remember_browser(browser)
            page = ExistingContext(browser).pages[0]
            page.script("activate")
            if action in {"go_to", "search"}:
                url = params.get("url", "")
                if action == "search":
                    url = _SEARCH_ENGINES.get(params.get("engine", "google"), _SEARCH_ENGINES["google"]) + quote_plus(params.get("query", ""))
                page.goto(safe_url(_normalize_url(url)))
                result = "Navigated the existing " + page.app + " tab."
            elif action == "get_url":
                result = page.url
            elif action == "get_text":
                result = page.locator("body").inner_text()[-24000:] if page.dom else "Browser scripting is unavailable. Use the existing screen and computer-control tools to read this page."
            elif action == "screenshot":
                import io
                from PIL import Image
                from pathlib import Path
                path = Path(params.get("path") or (Path.home()/"Downloads"/"friday-browser.png")).expanduser()
                Image.open(io.BytesIO(page.screenshot())).save(path)
                result = str(path)
            elif action in {"scroll", "press"}:
                if action == "press":
                    import pyautogui
                    key = str(params.get("key", "Enter")).lower()
                    keys = {"escape": "esc", "return": "enter", "meta": "command", "control": "ctrl"}
                    pyautogui.hotkey(*[keys.get(k, k) for k in key.replace("+", " ").split()])
                else:
                    amount = abs(int(params.get("amount", 500))) * (-1 if params.get("direction") == "up" else 1)
                    desktop_action({"action":"scroll", "amount":amount}, {})
                result = "Applied to your existing browser."
            elif action in {"back", "forward", "reload"} and page.dom:
                expression = {"back":"history.back()", "forward":"history.forward()", "reload":"location.reload()"}[action]
                page.evaluate("() => {" + expression + "; return true;}")
                result = "Applied to the existing tab."
            elif action in {"click", "type", "smart_click", "smart_type", "fill_form"} and page.dom:
                selector = params.get("selector")
                if selector:
                    controls = page.locator(selector).element_handles()
                else:
                    needle = str(params.get("description") if action.startswith("smart_") else params.get("text", "")).lower()
                    controls = [e for e in page.locator("button,a,input,textarea,[role=button],[contenteditable=true]").element_handles()
                        if e.is_visible() and needle and needle in str(e.evaluate("e=>(e.innerText||e.getAttribute('aria-label')||e.getAttribute('placeholder')||'').toLowerCase()"))]
                if len(controls) != 1:
                    raise ValueError("Observe a unique visible control first, or use the existing mouse/keyboard computer-control tools.")
                if action in {"type", "smart_type"}:
                    controls[0].fill(str(params.get("text", "")))
                elif action == "fill_form":
                    raise ValueError("Fill one observed field at a time using type.")
                else:
                    controls[0].click()
                result = "Applied to the observed control in your existing tab."
            else:
                result = "Use the existing screen and computer-control tools for this action. No browser was launched."
    except Exception as exc:
        result = str(exc)
    _log(player, result)
    return result


def _log(player, text: str):
    short = str(text)[:80]
    print(f"[Browser] {short}")
    if player:
        player.write_log(f"[browser] {short[:60]}")


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "browser_control",
    "description": "Controls any web browser. Use for: opening websites, searching the web, clicking elements, filling forms, scrolling, screenshots, navigation, any web-based task. Reuses an already running browser and active tab, keeping the user's signed-in session. Never launches browsers, profiles, windows or tabs. Use list_browsers then switch to save a browser preference. When DOM scripting is disabled use the existing screen/mouse/keyboard tools. Always pass the 'browser' parameter when the user specifies a browser (e.g. 'open in Edge', 'use Firefox', 'open Chrome'). Multiple browsers can run simultaneously.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "go_to | search | click | type | scroll | fill_form | smart_click | smart_type | get_text | get_url | press | new_tab | close_tab | screenshot | back | forward | reload | switch | list_browsers | close | close_all"
            },
            "browser": {
                "type": "STRING",
                "description": "Target browser: chrome | edge | firefox | opera | operagx | brave | vivaldi | safari. Omit to use the currently active browser."
            },
            "url": {
                "type": "STRING",
                "description": "URL for go_to / new_tab action"
            },
            "query": {
                "type": "STRING",
                "description": "Search query for search action"
            },
            "engine": {
                "type": "STRING",
                "description": "Search engine: google | bing | duckduckgo | yandex (default: google)"
            },
            "selector": {
                "type": "STRING",
                "description": "CSS selector for click/type"
            },
            "text": {
                "type": "STRING",
                "description": "Text to click or type"
            },
            "description": {
                "type": "STRING",
                "description": "Element description for smart_click/smart_type"
            },
            "direction": {
                "type": "STRING",
                "description": "up | down for scroll"
            },
            "amount": {
                "type": "INTEGER",
                "description": "Scroll amount in pixels (default: 500)"
            },
            "key": {
                "type": "STRING",
                "description": "Key name for press action (e.g. Enter, Escape, F5)"
            },
            "path": {
                "type": "STRING",
                "description": "Save path for screenshot"
            },
            "incognito": {
                "type": "BOOLEAN",
                "description": "Open in private/incognito mode"
            },
            "clear_first": {
                "type": "BOOLEAN",
                "description": "Clear field before typing (default: true)"
            }
        },
        "required": [
            "action"
        ]
    },
    "handler": browser_control,
}
