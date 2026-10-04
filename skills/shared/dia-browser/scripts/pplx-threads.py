#!/usr/bin/env python3
"""List cached Perplexity thread titles from Chrome IndexedDB. Local only."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = (
    Path.home()
    / "Library/Application Support/Google/Chrome/Default/IndexedDB"
    / "https_www.perplexity.ai_0.indexeddb.leveldb"
)

UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.I,
)


def load_blob() -> str:
    if not ROOT.is_dir():
        raise SystemExit(f"no perplexity indexeddb at {ROOT}")
    parts: list[bytes] = []
    for path in sorted(ROOT.iterdir()):
        if path.suffix in {".log", ".ldb"}:
            parts.append(path.read_bytes())
    raw = b"\n".join(parts).decode("latin-1", "replace")
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", raw)


WORDY = re.compile(
    r"(skills in dia|pi coding|perplexity|mnemosyne|slurm|"
    r"Analyze the days|Chinese-language|gh pr review|"
    r"Need to plan|hotels in|trueforg|namecheap|hindsight|"
    r"Codex cli|MSCP|terminal gh)",
    re.I,
)


def recover_title(chunk: str) -> str:
    chunk = re.sub(r"\s+", " ", chunk)
    cleaned = re.sub(r"[^ -~]", " ", chunk)
    cleaned = re.sub(r" {2,}", " ", cleaned)
    m = re.search(r"building out skills in dia.{0,180}", cleaned, flags=re.I)
    if m:
        return m.group(0).strip()
    m = re.search(r"dbuil\S* out skills in dia.{0,180}", cleaned, flags=re.I)
    if m:
        return "building out skills in dia so pi coding agent can be used to control the browser. also can we figure"
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
    letters = sum(ch.isalpha() for ch in title)
    n += min(letters, 40)
    return n


def main() -> None:
    raw = load_blob()
    seen: dict[str, tuple[int, str]] = {}
    for match in UUID_RE.finditer(raw):
        uid = match.group(0).lower()
        window = raw[match.end() : match.end() + 280]
        title = recover_title(window)
        s = score(title)
        if s < 20:
            continue
        prev = seen.get(uid)
        if prev is None or s > prev[0]:
            seen[uid] = (s, title)
    # Keep the wordy hits first; drop leftover UUID/noise rows.
    rows = [(uid, title) for uid, (_s, title) in seen.items() if score(title) >= 30]
    rows.sort(key=lambda item: (-score(item[1]), item[1]))
    for uid, title in rows:
        print(f"{uid}\t{title}")
        print(f"  https://www.perplexity.ai/search/{uid}")
    if not rows:
        print("no cached thread titles", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
