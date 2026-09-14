#!/usr/bin/env python3
"""Build an atop-vi catalog of live sessions + prompt buffers across harnesses."""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

try:
    import live as atop_live
except ImportError:
    atop_live = None  # type: ignore


def classify(path: str) -> str:
    p = path.replace("\\", "/").lower()
    name = os.path.basename(p)
    if name.startswith("herm-") or "/herm-" in p:
        return "herm"
    if "pi-editor" in p:
        return "pi"
    if name.startswith("claude-prompt") or "/.claude/prompt" in p:
        return "claude"
    if "/documents/codex/" in p or "/.codex/" in p and "prompt" in name:
        return "codex"
    if "nvim-prompt-workbench" in p or "nvim-workbench" in p:
        return "workbench"
    if name.startswith("atop-vi") or "/atop-vi." in p:
        return "atop-vi"
    if "cursor-prompt" in name or "/.cursor/" in p and "prompt" in name:
        return "cursor"
    if "opencode" in p and "prompt" in name:
        return "opencode"
    if name == "prompt.md":
        return "pi"
    if name.endswith(".md") and ("/tmp/" in p or "/var/folders/" in p or "/t/" in p):
        return "tmp"
    return "other"


def keep(path: str, harness: str) -> bool:
    name = os.path.basename(path)
    if "|" in name or name.endswith(".json") or name.startswith("snapshot-req"):
        return False
    if harness in {"herm", "pi", "claude", "codex", "cursor", "opencode", "workbench", "atop-vi", "tmp"}:
        return True
    lower = name.lower()
    return lower in {"prompt.md", "checkpoint.md"} or lower.startswith("prompt")


def load_inventory(path: Path) -> list[dict]:
    entries: list[dict] = []
    if not path.is_file() or path.stat().st_size == 0:
        return entries
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        sock = rec.get("socket") or ""
        pid = rec.get("pid")
        for buf in rec.get("buffers") or []:
            fpath = buf.get("path") or ""
            if not fpath:
                continue
            harness = classify(fpath)
            if not keep(fpath, harness):
                continue
            name = os.path.basename(fpath)
            stem = name[:-3] if name.endswith(".md") else name
            entries.append(
                {
                    "id": stem,
                    "harness": harness,
                    "kind": "prompt",
                    "path": fpath,
                    "live": True,
                    "pid": pid,
                    "buffer": buf.get("buffer"),
                    "socket": sock,
                    "modified": bool(buf.get("modified")),
                    "state": "live",
                    "activity": "",
                }
            )
    return entries


def scan_disk() -> list[dict]:
    entries: list[dict] = []
    roots = {Path(tempfile.gettempdir()), Path("/tmp"), Path("/private/tmp")}
    tmp = os.environ.get("TMPDIR")
    if tmp:
        roots.add(Path(tmp))
    seen: set[str] = set()

    def add(p: Path) -> None:
        try:
            if not p.is_file():
                return
            key = str(p.resolve())
        except OSError:
            return
        if key in seen:
            return
        seen.add(key)
        harness = classify(key)
        if not keep(key, harness):
            return
        name = p.name
        stem = name[:-3] if name.endswith(".md") else name
        entries.append(
            {
                "id": stem,
                "harness": harness,
                "kind": "prompt",
                "path": key,
                "live": False,
                "pid": None,
                "buffer": None,
                "socket": None,
                "modified": False,
                "state": "disk",
                "activity": "",
            }
        )

    globs = (
        "herm-*.md",
        "claude-prompt-*.md",
        "cursor-prompt-*.md",
        "pi-editor-*/prompt.md",
        "atop-vi*.md",
        "nvim-workbench-herm-*/*",
        "nvim-workbench-*/original.md",
        "nvim-workbench-*/candidate*.md",
    )
    for root in roots:
        if not root.is_dir():
            continue
        for pattern in globs:
            try:
                for p in root.glob(pattern):
                    add(p)
            except OSError:
                continue

    backup = Path.home() / ".claude" / "prompt-backups"
    if backup.is_dir():
        backups = sorted(
            backup.glob("claude-prompt-*.md"),
            key=lambda p: p.stat().st_mtime if p.exists() else 0,
            reverse=True,
        )
        for p in backups[:8]:
            add(p)
    return entries


def session_entries(snapshot: dict | None = None) -> list[dict]:
    if snapshot is None:
        if atop_live is None:
            return []
        snapshot = atop_live.collect()
    out = []
    for s in snapshot.get("sessions") or []:
        target = s.get("tmux_target") or s.get("sid") or ""
        prompt = s.get("prompt") or {}
        path = prompt.get("path") or f"live:{s.get('sid')}"
        out.append(
            {
                "id": target,
                "harness": s.get("harness") or "unknown",
                "kind": "session",
                "path": path,
                "live": True,
                "pid": s.get("pid"),
                "buffer": None,
                "socket": None,
                "modified": False,
                "state": s.get("state") or "live",
                "activity": s.get("activity") or s.get("title") or "",
                "sid": s.get("sid"),
                "tmux_target": s.get("tmux_target") or "",
            }
        )
    return out


def merge(live: list[dict], disk: list[dict], sessions: list[dict] | None = None) -> list[dict]:
    by_path: dict[str, dict] = {}
    for e in disk + live:
        path = e["path"]
        prev = by_path.get(path)
        if prev is None or (e.get("live") and not prev.get("live")):
            by_path[path] = e
    out = list(by_path.values()) + list(sessions or [])
    kind_order = {"session": 0, "prompt": 1}
    order = [
        "atop-vi",
        "hermes",
        "herm",
        "pi",
        "claude",
        "claude-code",
        "codex",
        "cursor",
        "opencode",
        "workbench",
        "tmp",
        "other",
        "unknown",
    ]
    state_order = {"busy": 0, "compact": 1, "live": 2, "idle": 3, "disk": 4}

    def key(e: dict) -> tuple:
        return (
            kind_order.get(e.get("kind") or "prompt", 9),
            state_order.get(e.get("state") or "", 9),
            order.index(e["harness"]) if e.get("harness") in order else 99,
            e.get("path") or "",
        )

    out.sort(key=key)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="atop-vi prompt + live session catalog")
    ap.add_argument("--inventory", type=Path, help="jsonl from nvim socket list")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--no-disk", action="store_true")
    ap.add_argument("--no-sessions", action="store_true")
    ap.add_argument("--live", type=Path, help="atop.live.v1 json to merge")
    args = ap.parse_args()
    live = load_inventory(args.inventory) if args.inventory else []
    disk = [] if args.no_disk else scan_disk()
    snapshot = None
    if args.live and args.live.is_file():
        snapshot = json.loads(args.live.read_text(encoding="utf-8"))
    elif atop_live is not None and not args.no_sessions:
        snapshot = atop_live.collect()
    sessions = [] if args.no_sessions else session_entries(snapshot)
    catalog = {
        "schema": "atop-vi.catalog.v1",
        "live_schema": "atop.live.v1",
        "counts": (snapshot or {}).get("counts"),
        "layers": (snapshot or {}).get("layers"),
        "entries": merge(live, disk, sessions),
    }
    args.out.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
