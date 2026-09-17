"""Realtime voice harness primitives — filter + a-top world brief. No local LLM."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from engine import (  # noqa: E402
    DEFAULT_CONTINUATION,
    apply_tts,
    context_from_env,
    normalize_utterance,
)
from schema import load_bundle  # noqa: E402

BANNED_WORKING = {
    "i'm working on it",
    "i am working on it",
    "working on it",
    "i'm on it",
}
BANNED_COS_TIMEOUT = {
    "chief of staff did not reply",
    "the chief of staff did not reply",
    "chief of staff didn't reply",
    "cos did not reply",
    "cos didn't reply",
}


def _atop_entries() -> list[dict[str, Any]]:
    atop = HERE.parent / "atop"
    if str(atop) not in sys.path:
        sys.path.insert(0, str(atop))
    try:
        from catalog import merge, scan_disk  # type: ignore
    except ImportError:
        return []
    try:
        return merge([], scan_disk())
    except OSError:
        return []


def world_brief(entries: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Deterministic a-top / a-top vi snapshot. Safe to speak aloud."""
    rows = list(entries) if entries is not None else _atop_entries()
    live = [row for row in rows if row.get("live")]
    dirty = [row for row in rows if row.get("modified")]
    live_counts = Counter(str(row.get("harness") or "other") for row in live)
    all_counts = Counter(str(row.get("harness") or "other") for row in rows)
    speakable = _speakable(len(live), len(dirty), live_counts, all_counts)
    return {
        "schema": "aos.voice.world.v1",
        "live": len(live),
        "modified": len(dirty),
        "buffers": len(rows),
        "harness": dict(all_counts),
        "live_harness": dict(live_counts),
        "dirty_ids": [str(row.get("id") or "") for row in dirty[:6] if row.get("id")],
        "speakable": speakable,
    }


def _speakable(live: int, dirty: int, live_counts: Counter, all_counts: Counter) -> str:
    if live <= 0 and not all_counts:
        return DEFAULT_CONTINUATION
    if live <= 0:
        return "Atop has on-disk prompt buffers. Continuing from the last confirmed state."
    top = live_counts.most_common(1)[0]
    name, count = top
    if dirty:
        return (
            f"Atop shows {live} live {name} buffer{'s' if live != 1 else ''} "
            f"and {dirty} dirty. Continuing from that snapshot."
        )
    return (
        f"Atop shows {live} live {name} buffer{'s' if live != 1 else ''}. "
        "Continuing from there."
    )


def _banned(text: str) -> bool:
    key = normalize_utterance(text)
    return key in BANNED_WORKING or key in BANNED_COS_TIMEOUT


def filter_transcript(
    text: str,
    *,
    ctx: dict[str, Any] | None = None,
    bundle: dict[str, Any] | None = None,
    world: dict[str, Any] | None = None,
    root: Path | None = None,
    home: Path | None = None,
) -> dict[str, Any]:
    """Apply aos.policy stream.tts and never emit a banned exact sentence."""
    ctx = ctx or context_from_env()
    bundle = bundle or load_bundle(root, home)
    snapshot = world if world is not None else world_brief()
    fallback = str(snapshot.get("speakable") or DEFAULT_CONTINUATION)
    raw = text or ""
    if not raw.strip():
        return {
            "schema": "aos.voice.tick.v1",
            "speech": fallback,
            "source": "timeout",
            "world": snapshot,
        }
    speech = apply_tts(bundle, raw, ctx, fallback=fallback)
    source = "passthrough" if speech == raw.strip() else "rewrite"
    if _banned(speech):
        speech = fallback
        source = "rewrite"
    return {
        "schema": "aos.voice.tick.v1",
        "speech": speech,
        "source": source,
        "world": snapshot,
    }


def timeout_speech(
    *,
    world: dict[str, Any] | None = None,
    reason: str = "empty",
) -> dict[str, Any]:
    snapshot = world if world is not None else world_brief()
    return {
        "schema": "aos.voice.tick.v1",
        "speech": str(snapshot.get("speakable") or DEFAULT_CONTINUATION),
        "source": "timeout",
        "reason": reason,
        "world": snapshot,
    }


def tick(text: str | None = None, **kwargs: Any) -> dict[str, Any]:
    if text is None or not str(text).strip():
        return timeout_speech(**{k: kwargs[k] for k in ("world", "reason") if k in kwargs})
    return filter_transcript(str(text), **kwargs)


def dump(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2) + "\n"
