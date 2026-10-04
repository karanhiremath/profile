#!/usr/bin/env python3
"""pi <> Perplexity bridge: catalog, live Chrome tab, official API, notes sync.

Does not steal Chrome cookies or call Perplexity's undocumented REST API.
Live tab control uses AppleScript on signed-in Chrome Default (no CDP).
New searches route to the official Agent/Search API when a key and quota
exist, otherwise to the signed-in web session.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import api as pplx_api
import chrome as pplx_chrome
import router as pplx_router

HOME = Path.home()
STATE = Path(os.environ.get("PI_PERPLEXITY_STATE", HOME / ".local/share/pi-perplexity"))
CATALOG = STATE / "catalog.jsonl"
EXPORTS = STATE / "exports"
NOTES_ROOT = Path(os.environ.get("PERSONAL_NOTES_ROOT", HOME / "src/notes"))
NOTES_PPLX = NOTES_ROOT / "03_tech/agentic-os/fleet/perplexity"
NOTES_UPDATES = NOTES_ROOT / "03_tech/agentic-os/fleet/updates"
INDEXEDDB = (
    HOME
    / "Library/Application Support/Google/Chrome/Default/IndexedDB"
    / "https_www.perplexity.ai_0.indexeddb.leveldb"
)
DOWNLOADS = HOME / "Downloads"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
LIBRARY_URL = "https://www.perplexity.ai/library"
WORKSPACE_URL = "https://www.perplexity.ai/projects"
SETTINGS_URL = "https://www.perplexity.ai/account/settings"
EXPORT_URL = "https://www.perplexity.ai/account"
DATAREQUEST_URL = "https://perplexity.typeform.com/datarequest"

UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.I,
)
WORDY = re.compile(
    r"(skills in dia|pi coding|perplexity|mnemosyne|slurm|"
    r"Analyze the days|Chinese-language|gh pr review|"
    r"Need to plan|hotels in|trueforg|namecheap|hindsight|"
    r"Codex cli|MSCP|terminal gh|art Basel|Hawaii|italy|robotics)",
    re.I,
)
EXPORT_ZIP_RE = re.compile(r"perplexity.*export.*\.zip$", re.I)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_state() -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    EXPORTS.mkdir(parents=True, exist_ok=True)


def load_blob() -> str:
    if not INDEXEDDB.is_dir():
        return ""
    parts: list[bytes] = []
    for path in sorted(INDEXEDDB.iterdir()):
        if path.suffix in {".log", ".ldb"}:
            parts.append(path.read_bytes())
    raw = b"\n".join(parts).decode("latin-1", "replace")
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", raw)


def recover_title(chunk: str) -> str:
    chunk = re.sub(r"\s+", " ", chunk)
    cleaned = re.sub(r"[^ -~]", " ", chunk)
    cleaned = re.sub(r" {2,}", " ", cleaned)
    m = re.search(r"building out skills in dia.{0,180}", cleaned, flags=re.I)
    if m:
        return m.group(0).strip()[:220]
    m = re.search(r"dbuil\S* out skills in dia.{0,180}", cleaned, flags=re.I)
    if m:
        return (
            "building out skills in dia so pi coding agent can be used "
            "to control the browser. also can we figure"
        )
    m = re.search(r"[A-Za-z][A-Za-z0-9 /+?&.,:;'\-]{18,160}", cleaned)
    return (m.group(0).strip() if m else "")[:180]


def score(title: str) -> int:
    if not title:
        return 0
    n = 0
    if WORDY.search(title):
        n += 50
    if UUID_RE.search(title):
        n -= 20
    n += min(sum(ch.isalpha() for ch in title), 40)
    return n


def scan_indexeddb() -> list[dict]:
    raw = load_blob()
    if not raw:
        return []
    seen: dict[str, tuple[int, str]] = {}
    for match in UUID_RE.finditer(raw):
        uid = match.group(0).lower()
        title = recover_title(raw[match.end() : match.end() + 280])
        s = score(title)
        if s < 30:
            continue
        prev = seen.get(uid)
        if prev is None or s > prev[0]:
            seen[uid] = (s, title)
    rows = [
        {
            "id": uid,
            "title": title,
            "url": f"https://www.perplexity.ai/search/{uid}",
            "source": "chrome-indexeddb",
        }
        for uid, (_s, title) in seen.items()
    ]
    rows.sort(key=lambda r: r["title"].lower())
    return rows


def write_catalog(rows: list[dict]) -> None:
    ensure_state()
    with CATALOG.open("w") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_catalog() -> list[dict]:
    if not CATALOG.is_file():
        return []
    out = []
    for line in CATALOG.read_text().splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out


def open_chrome(url: str) -> None:
    if not Path(CHROME).is_file():
        raise SystemExit("Google Chrome is missing")
    subprocess.run(["open", "-a", "Google Chrome", url], check=False)


def cmd_lookup(query: str) -> int:
    rows = read_catalog() or scan_indexeddb()
    q = query.strip().lower()
    hits = [r for r in rows if not q or q in r["title"].lower() or q in r["id"]]
    if not hits:
        print("no catalog hits", file=sys.stderr)
        return 1
    for row in hits:
        print(f"{row['id']}\t{row['title']}")
        print(f"  {row['url']}")
    return 0


def cmd_context() -> int:
    rows = read_catalog() or scan_indexeddb()
    print("Goal: navigate Perplexity offerings with existing chat history")
    print("Scope: personal")
    print("Known facts:")
    print("- Bridge: pi-p / pi-perplexity (profile bin/pi-perplexity)")
    print("- Signed-in Chrome Default is the live Perplexity session (AppleScript, no CDP)")
    print("- New asks: official Agent/Search API if PERPLEXITY_API_KEY + quota, else the live tab")
    print("- Official MCP: https://api.perplexity.ai/mcp (not in this Cursor-bridge tool list until Connect)")
    print(f"- Catalog rows: {len(rows)} at {CATALOG}")
    print(f"- Notes index: {NOTES_PPLX / 'index.md'}")
    print("Constraints:")
    print("- Do not steal cookies or call undocumented Perplexity REST APIs")
    print("- Do not dump full thread bodies or secrets into the ledger")
    print("- Work-private Perplexity spaces stay out of personal notes")
    print("- Enable View → Developer → Allow JavaScript from Apple Events for read/steer/md")
    print("Relevant files/links:")
    print(f"- {LIBRARY_URL}")
    print(f"- {SETTINGS_URL}")
    for row in rows[:8]:
        print(f"- {row['url']}  {row['title'][:80]}")
    print("Next requested action: pi-p tabs | pi-p read | pi-p search <q> | pi-p steer <text>")
    print("Done when: the live pane is read/steered or the API/browser search returned")
    return 0


def _print_json_or_text(as_json: bool, payload) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    if isinstance(payload, list):
        for row in payload:
            mark = "*" if row.get("active") else " "
            print(f"{mark} {row.get('window')}:{row.get('tab')}\t{row.get('title')}\t{row.get('url')}")
        return
    if isinstance(payload, dict) and payload.get("markdown"):
        print(payload["markdown"])
        return
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def cmd_tabs(as_json: bool) -> int:
    try:
        rows = pplx_chrome.list_tabs()
    except pplx_chrome.ChromeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    _print_json_or_text(as_json, rows)
    return 0 if rows else 1


def cmd_focus(match: str) -> int:
    try:
        row = pplx_chrome.focus_tab(match)
    except pplx_chrome.ChromeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"focused {row['window']}:{row['tab']}  {row['title']}")
    print(row["url"])
    return 0


def _active_tab() -> dict | None:
    try:
        tabs = pplx_chrome.list_tabs()
    except pplx_chrome.ChromeError:
        return None
    return next((row for row in tabs if row.get("active")), tabs[0] if tabs else None)


def cmd_read(as_json: bool) -> int:
    try:
        data = pplx_chrome.execute_js("read")
    except pplx_chrome.ChromeError as exc:
        msg = str(exc)
        if "JavaScript from Apple Events" in msg:
            row = _active_tab()
            if row:
                payload = {
                    "ok": False,
                    "js_enabled": False,
                    "fallback": "tab-metadata",
                    "url": row["url"],
                    "title": row["title"],
                    "window": row["window"],
                    "tab": row["tab"],
                    "error": msg,
                    "next": (
                        "Enable View → Developer → Allow JavaScript from Apple Events, "
                        "then retry pi-p read."
                    ),
                }
                _print_json_or_text(as_json, payload)
                return 0
        print(msg, file=sys.stderr)
        return 1
    _print_json_or_text(as_json, data)
    return 0


def cmd_md(out: str) -> int:
    try:
        data = pplx_chrome.execute_js("md")
    except pplx_chrome.ChromeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    dest = Path(out) if out else STATE / "downloads" / f"{utc_now().strftime('%Y%m%dT%H%MZ')}.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(data.get("markdown") or "", encoding="utf-8")
    print(str(dest))
    print(data.get("url", ""))
    return 0


def cmd_steer(text: str, dry: bool = False) -> int:
    if not text.strip() and not dry:
        print("steer needs a prompt", file=sys.stderr)
        return 2
    try:
        data = pplx_chrome.execute_js("fill" if dry else "steer", text)
    except pplx_chrome.ChromeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


def cmd_new(query: str) -> int:
    url = pplx_router.search_url(query) if query.strip() else "https://www.perplexity.ai/"
    pplx_chrome.open_url(url, new_tab=True)
    print(url)
    return 0


def cmd_search(query: str, via: str, preset: str, dry: bool = False) -> int:
    decision = pplx_router.decide("search", via)
    print(f"route via={decision['via']} reason={decision['reason']}", file=sys.stderr)
    if dry:
        print(json.dumps({**decision, "query": query, "preset": preset, "dry": True}, indent=2))
        return 0
    if decision["via"] == "browser":
        url = pplx_router.search_url(query)
        pplx_chrome.open_url(url, new_tab=True)
        print(url)
        return 0
    try:
        result = pplx_api.ask(query, preset=preset)
    except Exception as exc:
        print(f"api failed ({exc}); browser fallback", file=sys.stderr)
        url = pplx_router.search_url(query)
        pplx_chrome.open_url(url, new_tab=True)
        print(url)
        return 0
    print(result.get("text") or json.dumps(result, ensure_ascii=False, indent=2))
    if result.get("via"):
        print(f"via={result['via']}", file=sys.stderr)
    return 0


def cmd_usage() -> int:
    print(json.dumps(pplx_api.usage_status(), indent=2))
    return 0


def cmd_route(action: str, via: str) -> int:
    if not action:
        print(json.dumps(pplx_router.split(via), indent=2))
        return 0
    print(json.dumps(pplx_router.decide(action, via), indent=2))
    return 0


def cmd_chrome_prep() -> int:
    print(json.dumps(pplx_chrome.chrome_prep(), indent=2))
    return 0


def cmd_mcp_status() -> int:
    print(json.dumps(pplx_api.mcp_config(), indent=2))
    return 0


def cmd_mcp_install() -> int:
    print(json.dumps(pplx_api.install_mcp(), indent=2))
    return 0


def _focus_or_open(url_needles: tuple[str, ...], fallback_url: str) -> int:
    try:
        tabs = pplx_chrome.list_tabs()
    except pplx_chrome.ChromeError:
        tabs = []
    hits = [row for row in tabs if any(n in row["url"].lower() for n in url_needles)]
    if hits:
        row = next((h for h in hits if h.get("active")), hits[0])
        try:
            focused = pplx_chrome.focus_tab(f"{row['window']}:{row['tab']}")
        except pplx_chrome.ChromeError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(f"focused {focused['window']}:{focused['tab']}  {focused['title']}")
        print(focused["url"])
        return 0
    pplx_chrome.open_url(fallback_url, new_tab=True)
    print(fallback_url)
    return 0


def cmd_workspace() -> int:
    return _focus_or_open(("/projects", "/spaces", "/workspace"), WORKSPACE_URL)


def cmd_open(target: str) -> int:
    t = target.strip().lower()
    if t in {"", "library"}:
        return _focus_or_open(("/library",), LIBRARY_URL)
    if t in {"workspace", "spaces", "space"}:
        return cmd_workspace()
    if t in {"export", "settings", "account"}:
        open_chrome(EXPORT_URL)
        open_chrome(SETTINGS_URL)
        return 0
    if t in {"datarequest", "gdpr"}:
        open_chrome(DATAREQUEST_URL)
        return 0
    if UUID_RE.fullmatch(t):
        open_chrome(f"https://www.perplexity.ai/search/{t}")
        return 0
    rows = read_catalog() or scan_indexeddb()
    hits = [r for r in rows if t in r["title"].lower() or t in r["id"]]
    if len(hits) == 1:
        open_chrome(hits[0]["url"])
        return 0
    if not hits:
        print(f"no open target: {target}", file=sys.stderr)
        return 1
    print("ambiguous; pick a uuid:", file=sys.stderr)
    for row in hits[:12]:
        print(f"{row['id']}\t{row['title']}", file=sys.stderr)
    return 2


def find_download_zips() -> list[Path]:
    hits = []
    if DOWNLOADS.is_dir():
        for path in DOWNLOADS.iterdir():
            if path.is_file() and EXPORT_ZIP_RE.search(path.name):
                hits.append(path)
    return sorted(hits, key=lambda p: p.stat().st_mtime, reverse=True)


def ingest_export_zip(path: Path) -> list[dict]:
    dest = EXPORTS / path.name
    if path.resolve() != dest.resolve():
        shutil.copy2(path, dest)
    rows: list[dict] = []
    with zipfile.ZipFile(dest) as zf:
        for name in zf.namelist():
            if not name.endswith((".json", ".jsonl")):
                continue
            with zf.open(name) as fh:
                try:
                    raw = fh.read().decode("utf-8", "replace")
                except Exception:
                    continue
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            items = data if isinstance(data, list) else data.get("threads") or data.get("conversations") or []
            if isinstance(data, dict) and not items:
                for key, val in data.items():
                    if isinstance(val, list) and val and isinstance(val[0], dict):
                        items = val
                        break
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                uid = str(item.get("id") or item.get("uuid") or item.get("thread_id") or "")
                title = str(item.get("title") or item.get("query") or item.get("first_query") or "")[:220]
                if not uid and not title:
                    continue
                if not uid:
                    uid = f"export-{abs(hash(title))}"
                rows.append(
                    {
                        "id": uid,
                        "title": title or uid,
                        "url": item.get("url")
                        or (f"https://www.perplexity.ai/search/{uid}" if UUID_RE.fullmatch(uid) else ""),
                        "source": f"export:{path.name}",
                    }
                )
    return rows


def cmd_export_request() -> int:
    print("Opening signed-in Chrome to Perplexity account/settings.")
    print("If Export Data is visible, request it. The ZIP lands in ~/Downloads.")
    print("Then: pi-p ingest-export")
    print(f"Official fallback form: {DATAREQUEST_URL}")
    open_chrome(EXPORT_URL)
    open_chrome(SETTINGS_URL)
    zips = find_download_zips()
    if zips:
        print("already-downloaded:")
        for path in zips:
            print(f"  {path}")
    return 0


def cmd_ingest_export() -> int:
    zips = find_download_zips()
    if not zips:
        print("no perplexity export zip in ~/Downloads", file=sys.stderr)
        return 1
    catalog = {r["id"]: r for r in read_catalog()}
    added = 0
    for path in zips:
        for row in ingest_export_zip(path):
            if row["id"] not in catalog:
                added += 1
            catalog[row["id"]] = row
    write_catalog(list(catalog.values()))
    print(f"ingested {len(zips)} zip(s); catalog now {len(catalog)} rows (+{added} new)")
    return 0


def write_notes(rows: list[dict]) -> Path | None:
    if not NOTES_ROOT.is_dir():
        print(f"personal notes root missing: {NOTES_ROOT}", file=sys.stderr)
        return None
    NOTES_PPLX.mkdir(parents=True, exist_ok=True)
    (NOTES_PPLX / "threads").mkdir(parents=True, exist_ok=True)
    now = utc_now()
    index = NOTES_PPLX / "index.md"
    lines = [
        "---",
        "kind: perplexity-catalog",
        "scope: personal",
        f"timestamp: {now.isoformat()}",
        "privacy: personal",
        "---",
        "# Perplexity catalog",
        "",
        "Metadata-first. Full thread bodies stay in `~/.local/share/pi-perplexity`.",
        "Work-private spaces are out of scope on this host.",
        "",
        f"Rows: {len(rows)}",
        "",
        "| id | title | url |",
        "|----|-------|-----|",
    ]
    for row in rows:
        title = row["title"].replace("|", "/")
        lines.append(f"| `{row['id']}` | {title} | {row.get('url','')} |")
        thread = NOTES_PPLX / "threads" / f"{row['id']}.md"
        if not thread.exists():
            thread.write_text(
                "\n".join(
                    [
                        "---",
                        "kind: perplexity-thread",
                        "scope: personal",
                        f"thread_id: {row['id']}",
                        f"source: {row.get('source', 'unknown')}",
                        "privacy: personal",
                        "---",
                        f"# {row['title']}",
                        "",
                        f"- url: {row.get('url','')}",
                        f"- source: {row.get('source','')}",
                        "",
                        "Body not stored here. Open with `pi-p open <id>`.",
                        "",
                    ]
                )
            )
    index.write_text("\n".join(lines) + "\n")
    day = now.strftime("%Y-%m-%d")
    stamp = now.strftime("%Y%m%dT%H%MZ")
    update_dir = NOTES_UPDATES / day
    update_dir.mkdir(parents=True, exist_ok=True)
    update = update_dir / f"{stamp}--pi-p--perplexity-sync.md"
    update.write_text(
        "\n".join(
            [
                "---",
                "kind: agent-update",
                "scope: personal",
                f"timestamp: {now.isoformat()}",
                "agent: pi-perplexity",
                "surface: chrome",
                "session_id: pi-p",
                "project: agentic-os",
                "status: done",
                "privacy: personal",
                "source_ref: 03_tech/agentic-os/fleet/perplexity/index.md",
                "next_action: pi-p lookup <query> or pi-p open library",
                "---",
                f"# Agent update — {now.isoformat()} — Perplexity catalog sync",
                "",
                "## Since last update",
                f"- Catalog rows: {len(rows)}",
                f"- Index: `03_tech/agentic-os/fleet/perplexity/index.md`",
                "",
                "## Current",
                "- Bridge aliases: `pi-p`, `pi-perplexity`",
                "- Live tab: signed-in Chrome Default, open-only",
                "",
                "## Blockers / decisions needed",
                "- Official bulk export is account-dependent; request via Settings or the data-request form.",
                "",
                "## Next",
                "- Run `pi-p export-request` once, then `pi-p ingest-export` when the ZIP arrives.",
                "",
            ]
        )
    )
    return index


def cmd_sync() -> int:
    rows = scan_indexeddb()
    catalog = {r["id"]: r for r in rows}
    for path in find_download_zips():
        for row in ingest_export_zip(path):
            catalog[row["id"]] = row
    merged = list(catalog.values())
    merged.sort(key=lambda r: r["title"].lower())
    write_catalog(merged)
    index = write_notes(merged)
    print(f"catalog={len(merged)} state={CATALOG}")
    if index:
        print(f"notes={index}")
    return 0


def cmd_install_cron() -> int:
    label = "com.karan.pi-perplexity-sync"
    plist = HOME / "Library/LaunchAgents" / f"{label}.plist"
    exe = Path(__file__).resolve().parent / "pi-perplexity"
    log_dir = STATE / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    plist.parent.mkdir(parents=True, exist_ok=True)
    plist.write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>{label}</string>
  <key>ProgramArguments</key>
  <array>
    <string>{exe}</string>
    <string>sync</string>
  </array>
  <key>StartInterval</key><integer>21600</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>{log_dir / "sync.out.log"}</string>
  <key>StandardErrorPath</key><string>{log_dir / "sync.err.log"}</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>HOME</key><string>{HOME}</string>
    <key>PERSONAL_NOTES_ROOT</key><string>{NOTES_ROOT}</string>
  </dict>
</dict>
</plist>
"""
    )
    subprocess.run(["launchctl", "unload", str(plist)], check=False)
    subprocess.run(["launchctl", "load", str(plist)], check=False)
    print(f"loaded {plist} every 6h")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="pi-p", description="pi <> Perplexity bridge")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_lookup = sub.add_parser("lookup", help="search cached thread titles")
    p_lookup.add_argument("query", nargs="?", default="")
    sub.add_parser("context", help="print a context packet for a new agent")
    p_open = sub.add_parser("open", help="open library, workspace/spaces, export, or a thread")
    p_open.add_argument("target", nargs="?", default="library")
    p_tabs = sub.add_parser("tabs", help="list open Perplexity Chrome tabs")
    p_tabs.add_argument("--json", action="store_true")
    p_focus = sub.add_parser("focus", help="focus a Perplexity tab by uuid, title, or window:tab")
    p_focus.add_argument("match")
    p_read = sub.add_parser("read", help="read the front Perplexity pane as markdown")
    p_read.add_argument("--json", action="store_true")
    p_md = sub.add_parser("md", help="download the front search as markdown")
    p_md.add_argument("--out", default="")
    p_dl = sub.add_parser("download", help="alias for md")
    p_dl.add_argument("--out", default="")
    p_steer = sub.add_parser("steer", help="type a follow-up into the live composer and submit")
    p_steer.add_argument("text", nargs="*")
    p_steer.add_argument("--dry", action="store_true", help="fill composer only; do not submit")
    p_new = sub.add_parser("new", help="open a new Perplexity tab, optionally with a query")
    p_new.add_argument("query", nargs="*", default=[])
    p_search = sub.add_parser("search", help="ask: official API if keyed+quota, else live tab")
    p_search.add_argument("query", nargs="+")
    p_search.add_argument("--via", default="auto", choices=["auto", "api", "browser", "mcp"])
    p_search.add_argument("--preset", default="low", choices=["low", "medium", "high", "fast", "xhigh"])
    p_search.add_argument("--dry", action="store_true", help="print route only; no API call, no new tab")
    p_ask = sub.add_parser("ask", help="alias for search")
    p_ask.add_argument("query", nargs="+")
    p_ask.add_argument("--via", default="auto", choices=["auto", "api", "browser", "mcp"])
    p_ask.add_argument("--preset", default="low", choices=["low", "medium", "high", "fast", "xhigh"])
    p_ask.add_argument("--dry", action="store_true", help="print route only; no API call, no new tab")
    sub.add_parser("usage", help="API key / RPM / cooldown / MCP status")
    p_route = sub.add_parser("route", help="show API vs Chrome split (or one action)")
    p_route.add_argument("action", nargs="?", default="")
    p_route.add_argument("--via", default="auto")
    sub.add_parser("workspace", help="focus or open Perplexity Projects in signed-in Chrome")
    sub.add_parser("chrome-prep", help="prep Chrome for live pane JS (no CDP)")
    sub.add_parser("mcp-status", help="detect official Perplexity MCP config")
    sub.add_parser("mcp-install", help="add official remote + docs MCP to ~/.cursor/mcp.json (no API key)")
    sub.add_parser("export-request", help="open Settings/Account for official history download")
    sub.add_parser("ingest-export", help="ingest a Perplexity export ZIP from ~/Downloads")
    sub.add_parser("sync", help="rebuild catalog + personal notes index")
    sub.add_parser("install-cron", help="install home-mac-mini launchd sync (6h)")
    args = parser.parse_args()
    ensure_state()
    if args.cmd == "lookup":
        return cmd_lookup(args.query)
    if args.cmd == "context":
        return cmd_context()
    if args.cmd == "open":
        return cmd_open(args.target)
    if args.cmd == "workspace":
        return cmd_workspace()
    if args.cmd == "tabs":
        return cmd_tabs(args.json)
    if args.cmd == "focus":
        return cmd_focus(args.match)
    if args.cmd == "read":
        return cmd_read(args.json)
    if args.cmd in {"md", "download"}:
        return cmd_md(getattr(args, "out", ""))
    if args.cmd == "steer":
        return cmd_steer(" ".join(args.text), dry=args.dry)
    if args.cmd == "new":
        return cmd_new(" ".join(args.query))
    if args.cmd in {"search", "ask"}:
        return cmd_search(" ".join(args.query), args.via, args.preset, dry=args.dry)
    if args.cmd == "usage":
        return cmd_usage()
    if args.cmd == "route":
        return cmd_route(args.action, args.via)
    if args.cmd == "chrome-prep":
        return cmd_chrome_prep()
    if args.cmd == "mcp-status":
        return cmd_mcp_status()
    if args.cmd == "mcp-install":
        return cmd_mcp_install()
    if args.cmd == "export-request":
        return cmd_export_request()
    if args.cmd == "ingest-export":
        return cmd_ingest_export()
    if args.cmd == "sync":
        return cmd_sync()
    if args.cmd == "install-cron":
        return cmd_install_cron()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
