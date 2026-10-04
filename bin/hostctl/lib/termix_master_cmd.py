"""Allowlist parser for the termix-master hostctl SSH ForceCommand."""

from __future__ import annotations

import re

ALLOWED = {
    ("status",),
    ("hosts",),
    ("role",),
    ("up",),
    ("down",),
    ("termix",),
    ("termix", "status"),
    ("termix", "up"),
    ("termix", "down"),
    ("termix", "serve"),
    ("omarchy",),
    ("omarchy", "status"),
    ("omarchy", "probe"),
    ("omarchy", "ports"),
    ("omarchy", "up"),
    ("omarchy", "down"),
    ("omarchy", "bind"),
}

HELP = """termix-master hostctl on khire-mac-mini
Allowed: status hosts role up down
         termix [status|up|down|serve]
         omarchy [status|probe|ports|up|down|bind]
This key cannot open a shell. Isolated tailnet hosts stay out of this allowlist.
"""


_TERMIX_EXEC = re.compile(
    r"^\(\s*(?P<cmd>.*?)\s*\)\s*printf\s+'\\n__TERMIX_EXIT=%d\\n'\s+\"\$\?\"\s*$",
    re.S,
)


def unwrap_command(raw: str | None) -> str:
    text = raw or ""
    match = _TERMIX_EXEC.match(text.strip())
    if match:
        return match.group("cmd").strip()
    return text.strip()


def parse_command(raw: str | None) -> list[str] | str:
    """Return hostctl argv (without the binary) or 'help'. Raise ValueError if refused."""
    text = unwrap_command(raw)
    if not text or text in {"help", "?", "-h", "--help"}:
        return "help"
    parts = text.split()
    if parts[0] == "hostctl":
        parts = parts[1:]
    if not parts:
        return "help"
    if any(not part.replace("-", "").isalnum() for part in parts):
        raise ValueError("refused: only hostctl allowlist tokens are permitted")
    key = tuple(parts)
    if key not in ALLOWED:
        raise ValueError(f"refused: {' '.join(parts)} is not a termix-master hostctl command")
    return list(key)
