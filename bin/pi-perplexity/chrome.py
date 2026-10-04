"""Signed-in Chrome Default control for Perplexity. AppleScript only, no CDP."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

CHROME_APP = "Google Chrome"
PANE_JS = Path(__file__).resolve().parent / "pane.js"
HOST = "perplexity.ai"
JS_OFF = (
    "Chrome has JavaScript from Apple Events turned off. "
    "In Google Chrome: View → Developer → Allow JavaScript from Apple Events. "
    "Then retry. No CDP is used."
)


class ChromeError(RuntimeError):
    pass


def run_osascript(source: str, timeout: float = 8) -> str:
    try:
        proc = subprocess.run(
            ["osascript", "-e", source],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise ChromeError(f"Chrome AppleScript timed out after {timeout}s") from exc
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "osascript failed").strip()
        if "JavaScript through AppleScript is turned off" in err:
            raise ChromeError(JS_OFF)
        raise ChromeError(err)
    return (proc.stdout or "").rstrip("\n")


def chrome_running() -> bool:
    out = run_osascript(
        'tell application "System Events" to (exists process "Google Chrome")'
    )
    return out.strip().lower() == "true"


def ensure_chrome() -> None:
    if not chrome_running():
        subprocess.run(["open", "-a", CHROME_APP], check=False)
        run_osascript('tell application "Google Chrome" to activate', timeout=6)


def list_tabs() -> list[dict]:
    ensure_chrome()
    raw = run_osascript(
        """
tell application "Google Chrome"
  if (count of windows) is 0 then return "[]"
  set rows to ""
  set wi to 0
  repeat with w in windows
    set wi to wi + 1
    set ti to 0
    repeat with t in tabs of w
      set ti to ti + 1
      set u to URL of t
      if u contains "perplexity.ai" then
        set activeFlag to "0"
        if ti is (active tab index of w) then set activeFlag to "1"
        set rows to rows & wi & "\t" & ti & "\t" & activeFlag & "\t" & (title of t) & "\t" & u & linefeed
      end if
    end repeat
  end repeat
  return rows
end tell
""",
        timeout=8,
    )
    rows = []
    for line in raw.splitlines():
        parts = line.split("\t", 4)
        if len(parts) != 5:
            continue
        rows.append(
            {
                "window": int(parts[0]),
                "tab": int(parts[1]),
                "active": parts[2] == "1",
                "title": parts[3],
                "url": parts[4],
            }
        )
    return rows


def focus_tab(match: str) -> dict:
    needle = match.strip().lower()
    tabs = list_tabs()
    hits = []
    for row in tabs:
        blob = f"{row['title']} {row['url']}".lower()
        idx = f"{row['window']}:{row['tab']}"
        if needle in blob or needle == idx or needle == str(row["tab"]):
            hits.append(row)
    if not hits:
        raise ChromeError(f"no perplexity tab matches {match!r}")
    if len(hits) > 1 and not any(needle == f"{h['window']}:{h['tab']}" for h in hits):
        raise ChromeError(
            "ambiguous tab; pass window:tab\n"
            + "\n".join(f"{h['window']}:{h['tab']}\t{h['title']}\t{h['url']}" for h in hits[:8])
        )
    row = hits[0]
    run_osascript(
        f"""
tell application "Google Chrome"
  set w to window {row['window']}
  set active tab index of w to {row['tab']}
  set index of w to 1
  activate
end tell
"""
    )
    return row


def open_url(url: str, new_tab: bool = True) -> None:
    ensure_chrome()
    escaped = url.replace("\\", "\\\\").replace('"', '\\"')
    if new_tab:
        run_osascript(
            f"""
tell application "Google Chrome"
  activate
  if (count of windows) is 0 then
    make new window
  end if
  tell front window to make new tab with properties {{URL:"{escaped}"}}
end tell
"""
        )
        return
    subprocess.run(["open", "-a", CHROME_APP, url], check=False)


def js_status() -> dict:
    try:
        out = execute_js("probe")
        return {"enabled": True, "probe": out}
    except ChromeError as exc:
        return {"enabled": False, "error": str(exc)}


def execute_js(op: str, text: str = "") -> dict:
    if not PANE_JS.is_file():
        raise ChromeError(f"missing {PANE_JS}")
    ensure_chrome()
    prelude = (
        f"window.__PIP_OP = {json.dumps(op)};\n"
        f"window.__PIP_TEXT = {json.dumps(text)};\n"
    )
    script_path = Path("/tmp/pi-perplexity-pane.js")
    script_path.write_text(prelude + PANE_JS.read_text(), encoding="utf-8")
    posix = str(script_path)
    raw = run_osascript(
        f"""
set js to read POSIX file "{posix}" as «class utf8»
tell application "Google Chrome"
  if (count of windows) is 0 then return "{{}}"
  execute (active tab of front window) javascript js
end tell
""",
        timeout=10,
    )
    if not raw:
        raise ChromeError("Chrome JS returned empty (enable Apple Events JS, or no front tab)")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ChromeError(f"Chrome JS returned non-JSON: {raw[:240]}") from exc
    if not data.get("ok", True):
        raise ChromeError(data.get("error") or raw)
    return data


def _defaults_js_flag() -> bool | None:
    proc = subprocess.run(
        ["defaults", "read", "com.google.Chrome", "AppleEventsAllowJavaScript"],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() in {"1", "true", "TRUE"}


def _try_menu_enable() -> dict:
    """Best-effort View → Developer → Allow JavaScript from Apple Events."""
    script = """
tell application "Google Chrome" to activate
delay 0.3
tell application "System Events"
  tell process "Google Chrome"
    click menu item "Allow JavaScript from Apple Events" of menu "Developer" of menu item "Developer" of menu "View" of menu bar 1
  end tell
end tell
"""
    try:
        run_osascript(script, timeout=8)
        return {"ok": True, "error": None}
    except ChromeError as exc:
        err = str(exc)
        if "not allowed assistive access" in err or "-1719" in err:
            return {
                "ok": False,
                "error": "osascript lacks Accessibility; cannot click the Chrome menu",
            }
        return {"ok": False, "error": err}


def chrome_prep() -> dict:
    subprocess.run(
        ["defaults", "write", "com.google.Chrome", "AppleEventsAllowJavaScript", "-bool", "true"],
        check=False,
    )
    ensure_chrome()
    menu = _try_menu_enable()
    status = js_status()
    return {
        "js_enabled": status.get("enabled"),
        "defaults_AppleEventsAllowJavaScript": _defaults_js_flag(),
        "menu_click": menu,
        "menu": "Google Chrome → View → Developer → Allow JavaScript from Apple Events",
        "note": "The checkbox is the runtime gate. defaults write is not enough. Do not CDP-attach Chrome Default.",
        "next": None
        if status.get("enabled")
        else "In Google Chrome: View → Developer → Allow JavaScript from Apple Events, then pi-p read.",
        "error": status.get("error"),
    }
