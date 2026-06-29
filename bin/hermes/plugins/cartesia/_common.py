"""Shared Cartesia HTTP plumbing for the TTS + STT providers.

No vendor SDK dependency — talks to the Cartesia HTTP API directly via
``httpx`` (already vendored in the Hermes toolchain venv). Credentials are
read from ``~/.hermes/.env`` through Hermes' own ``get_env_value`` helper so
the key never has to be exported into the process environment.
"""

from __future__ import annotations

import os
from typing import Dict, Optional

BASE_URL_DEFAULT = "https://api.cartesia.ai"
# Only value the API currently accepts; override via env for forward-compat.
API_VERSION_DEFAULT = "2026-03-01"


def get_env(key: str) -> Optional[str]:
    """Read ``key`` from Hermes' env store, falling back to os.environ.

    ``hermes_cli.config.get_env_value`` resolves ``~/.hermes/.env`` (where
    ``hermes secrets`` / ``configure-machine`` write keys) in addition to the
    process environment; prefer it so a non-exported ``.env`` entry works.
    """
    try:
        from hermes_cli.config import get_env_value

        val = get_env_value(key)
        if val:
            return val
    except Exception:
        pass
    return os.environ.get(key)


def api_key() -> Optional[str]:
    return get_env("CARTESIA_API_KEY")


def base_url() -> str:
    """Canonical Cartesia endpoint switch (matches the bifrost repo convention).

    Default public prod; set ``CARTESIA_BASE_URL`` in ~/.hermes/.env to point at
    an internal target for validation — e.g. shared staging, on-prem
    (``http://localhost:8000``), or in-cluster (``http://api:8000``). The same
    server, paths, and key auth serve every environment.
    """
    return (get_env("CARTESIA_BASE_URL") or BASE_URL_DEFAULT).rstrip("/")


def stt_base_url() -> str:
    """STT endpoint, with an optional STT-only override.

    Mirrors inferno's ``CARTESIA_STT_BASE_URL`` / ``STT_BASE_URL`` convention so
    STT can target a different stack than TTS when validating; falls back to the
    shared :func:`base_url`.
    """
    return (
        get_env("CARTESIA_STT_BASE_URL")
        or get_env("STT_BASE_URL")
        or base_url()
    ).rstrip("/")


def api_version() -> str:
    return get_env("CARTESIA_VERSION") or API_VERSION_DEFAULT


def auth_headers() -> Dict[str, str]:
    key = api_key()
    if not key:
        raise RuntimeError(
            "CARTESIA_API_KEY is not set. Add it to ~/.hermes/.env "
            "(get a key at https://play.cartesia.ai/console)."
        )
    # Cartesia's model API (public + internal apps/api) canonically takes the
    # key in X-API-Key; Authorization: Bearer is also accepted. X-API-Key
    # matches the in-repo callers (inferno/s2s/stt.py, lora_app/create_voice.py).
    return {
        "X-API-Key": key,
        "Cartesia-Version": api_version(),
    }
