#!/usr/bin/env python3
"""Configure Hermes from a non-secret machine profile.

This script intentionally prints only pass/fail style status; it never prints
credential values. It may import Codex CLI OAuth tokens into Hermes' own auth
store when the profile requests it.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CODEX_BASE_URL = "https://chatgpt.com/backend-api/codex"
DEFAULT_PROVIDER = "openai-codex"
DEFAULT_MODEL = "gpt-5.5"


def _load_profile(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise SystemExit(f"ERROR: profile must be a mapping: {path}")
    return data


def _nested(data: dict[str, Any], *keys: str, default: Any = None) -> Any:
    cur: Any = data
    for key in keys:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def _ensure_empty_env_file() -> None:
    hermes_home = Path.home() / ".hermes"
    hermes_home.mkdir(mode=0o700, exist_ok=True)
    env_path = hermes_home / ".env"
    if not env_path.exists():
        env_path.write_text("# Managed by profile/bin/hermes/configure-machine. Do not commit secrets here.\n", encoding="utf-8")
        env_path.chmod(0o600)
        print("env_file=created")
    else:
        print("env_file=present")


def _import_codex_cli_tokens() -> bool:
    codex_home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).expanduser()
    auth_path = codex_home / "auth.json"
    if not auth_path.exists():
        print("codex_cli_auth=missing")
        return False
    payload = json.loads(auth_path.read_text(encoding="utf-8"))
    tokens = payload.get("tokens")
    if not isinstance(tokens, dict) or not tokens.get("access_token") or not tokens.get("refresh_token"):
        print("codex_cli_auth=invalid")
        return False

    from hermes_cli.auth import _save_codex_tokens  # noqa: PLC2701 - intentional private API use

    _save_codex_tokens(dict(tokens), payload.get("last_refresh"), label="codex-cli-import")
    print("codex_cli_auth=imported")
    return True


def _configure_model(provider: str, model: str, base_url: str) -> None:
    from hermes_cli.auth import _update_config_for_provider  # noqa: PLC2701 - intentional private API use
    from hermes_cli.config import load_config, save_config

    _update_config_for_provider(provider, base_url, default_model=model)
    cfg = load_config()
    model_cfg = dict(cfg.get("model") or {})
    model_cfg["provider"] = provider
    model_cfg["default"] = model
    if base_url:
        model_cfg["base_url"] = base_url.rstrip("/")
    cfg["model"] = model_cfg
    save_config(cfg)
    print(f"provider={provider}")
    print(f"model={model}")


def main() -> int:
    profile_path = Path(os.environ.get("PROFILE", "")).expanduser()
    profile = _load_profile(profile_path) if str(profile_path) else {}

    provider = os.environ.get("PROVIDER") or _nested(profile, "model", "provider", default=DEFAULT_PROVIDER)
    model = os.environ.get("MODEL") or _nested(profile, "model", "default", default=DEFAULT_MODEL)
    base_url = os.environ.get("BASE_URL") or _nested(profile, "model", "base_url", default=DEFAULT_CODEX_BASE_URL)
    import_codex = bool(_nested(profile, "auth", "import_codex_cli", default=True))
    if os.environ.get("SKIP_AUTH_IMPORT") == "1":
        import_codex = False

    _ensure_empty_env_file()
    if provider == "openai-codex" and import_codex:
        _import_codex_cli_tokens()
    else:
        print("codex_cli_auth=skipped")

    _configure_model(str(provider), str(model), str(base_url))
    print(f"profile={profile_path if profile_path.exists() else 'default'}")
    print(f"machine={os.environ.get('MACHINE', '')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
