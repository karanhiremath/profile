"""Opt-in, file-only, redacted event fanout for the offline spike."""

from __future__ import annotations

import json
import os
import stat
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from .core import Rejected, require


def sinks(env: dict[str, str]) -> list[Path]:
    require(
        env.get("CARTESIA_EVENT_PROFILE", "none") == "none", "unsupported_event_profile"
    )
    paths: list[Path] = []
    raw = env.get("CARTESIA_EVENT_SINKS", "[]")
    try:
        entries = json.loads(raw)
    except (ValueError, RecursionError):
        raise Rejected(
            "invalid_event_sinks", "Event sinks must be a JSON list of file sinks."
        ) from None
    require(isinstance(entries, list) and len(entries) <= 32, "invalid_event_sinks")
    for entry in entries:
        require(
            isinstance(entry, dict) and set(entry) == {"type", "path"},
            "invalid_event_sinks",
        )
        require(entry["type"] == "file", "unsupported_event_sink")
        require(
            isinstance(entry["path"], str)
            and 0 < len(entry["path"]) <= 4096
            and "\x00" not in entry["path"],
            "invalid_event_sinks",
        )
        paths.append(Path(entry["path"]).absolute())
    for key in ("CARTESIA_EVENT_BUSES", "CARTESIA_EVENT_BUS"):
        value = env.get(key, "")
        require(len(value) <= 16384, "invalid_event_sinks")
        for item in value.split(",") if key.endswith("BUSES") else [value]:
            if item.strip():
                require("\x00" not in item, "invalid_event_sinks")
                paths.append(Path(item.strip()).absolute())
    paths = list(dict.fromkeys(paths))
    require(len(paths) <= 32, "invalid_event_sinks")
    return paths


def emit(paths: list[Path], operation: str, status: str) -> None:
    event = {
        "schema_version": "cartesia.event.v1",
        "run_id": str(uuid4()),
        "tool": "aos-voice",
        "phase": operation,
        "status": status,
        "severity": "info" if status != "failed" else "error",
        "ts": datetime.now(UTC).isoformat(),
        "subject": {"mode": "fake", "executed": False},
        "artifact_dir": None,
        "correlation_ids": [],
        "redaction_class": "non_secret",
    }
    encoded = (json.dumps(event, separators=(",", ":")) + "\n").encode()
    for path in paths:
        try:
            fd = os.open(
                path,
                os.O_APPEND | os.O_CREAT | os.O_WRONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                0o600,
            )
            with os.fdopen(fd, "wb") as stream:
                info = os.fstat(stream.fileno())
                require(stat.S_ISREG(info.st_mode), "invalid_event_sink_file")
                for output in (1, 2):
                    other = os.fstat(output)
                    require(
                        (info.st_dev, info.st_ino) != (other.st_dev, other.st_ino),
                        "event_sink_is_output",
                    )
                stream.write(encoded)
        except (OSError, ValueError):
            raise Rejected(
                "event_sink_unavailable",
                "Cannot append to an explicitly configured event sink.",
            ) from None
