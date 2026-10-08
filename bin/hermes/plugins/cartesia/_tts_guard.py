"""Last-resort exact-sentence TTS guard when aos-policy is not on sys.path.

Isolated HERMES_HOME copies of this plugin must never speak the banned
stall or CoS-timeout sentences. Prefer `aos-policy voice filter`.
"""

from __future__ import annotations

import re

DEFAULT_CONTINUATION = (
    "Still with the last confirmed fleet snapshot. Next I'll check the live panes."
)

_BANNED = {
    "i'm working on it",
    "i am working on it",
    "working on it",
    "i'm on it",
    "chief of staff did not reply",
    "the chief of staff did not reply",
    "chief of staff didn't reply",
    "cos did not reply",
    "cos didn't reply",
}


def _norm(text: str) -> str:
    out = (text or "").strip().lower().replace("\u2019", "'")
    out = re.sub(r"[\"“”]", "", out)
    out = re.sub(r"[.!?…,;:]+$", "", out)
    return re.sub(r"\s+", " ", out).strip()


def _sentences(text: str) -> list[str]:
    parts = re.findall(r".+?(?:[.!?]+(?:\s+|$)|$)", text or "", flags=re.S)
    return [part for part in parts if part.strip()] or ([text] if text else [])


def filter_transcript(text: str, fallback: str = DEFAULT_CONTINUATION) -> str:
    raw = text or ""
    if not raw.strip():
        return fallback
    out: list[str] = []
    changed = False
    for part in _sentences(raw):
        if _norm(part) in _BANNED:
            gap = re.match(r".*?(\s*)$", part, flags=re.S)
            suffix = gap.group(1) if gap else ""
            out.append(fallback.rstrip().rstrip(".") + "." + suffix)
            changed = True
        else:
            out.append(part)
    spoken = ("".join(out) if changed else raw).strip()
    if not spoken or _norm(spoken) in _BANNED:
        return fallback
    return spoken
