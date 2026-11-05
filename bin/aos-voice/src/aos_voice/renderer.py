"""Byte/resize seam only. This module does not emulate or render a terminal."""

from __future__ import annotations

from hashlib import sha256
from typing import Protocol

from .core import generation, identifier, require


def capabilities() -> dict[str, object]:
    return {
        "schema": "aos.voice.renderer.v1",
        "backend": "fake-bytes",
        "ready": True,
        "terminal_rendering": False,
        "native_ghostty": "external-client-not-loaded",
        "libghostty_wasm": "unverified-not-bundled",
        "transport": "memory-only",
        "live_ready": False,
    }


class Renderer(Protocol):
    def feed(self, target: str, revision: int, data: bytes) -> None: ...
    def resize(self, target: str, revision: int, cols: int, rows: int) -> None: ...


class FakeRenderer:
    """Preserve PTY bytes unchanged and enforce target/generation on every frame."""

    def __init__(self, target: str, revision: int) -> None:
        require(identifier(target) and generation(revision))
        self.target = target
        self.revision = revision
        self.data = bytearray()
        self.cols = 80
        self.rows = 24

    def _pin(self, target: str, revision: int) -> None:
        require(target == self.target, "target_not_pinned")
        require(generation(revision) and revision == self.revision, "stale_generation")

    def feed(self, target: str, revision: int, data: bytes) -> None:
        self._pin(target, revision)
        require(
            isinstance(data, bytes) and len(self.data) + len(data) <= 1048576,
            "frame_limit",
        )
        self.data.extend(data)

    def resize(self, target: str, revision: int, cols: int, rows: int) -> None:
        self._pin(target, revision)
        require(
            type(cols) is int
            and type(rows) is int
            and 1 <= cols <= 1000
            and 1 <= rows <= 1000,
            "invalid_viewport",
        )
        self.cols, self.rows = cols, rows

    def summary(self) -> dict[str, object]:
        return {
            "backend": "fake-bytes",
            "terminal_rendering": False,
            "bytes": len(self.data),
            "sha256": sha256(self.data).hexdigest(),
            "cols": self.cols,
            "rows": self.rows,
        }
