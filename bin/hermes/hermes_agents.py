#!/usr/bin/env python3
"""Backend for the `agents` launcher: resolve a voice-validation profile and
materialize an isolated HERMES_HOME for it.

Each validation agent gets its own HERMES_HOME under
``$XDG_DATA_HOME/hermes-validation/<name>/`` so it never touches the operator's
main ~/.hermes. The home gets a derived ``config.yaml`` (Cartesia TTS+STT wired
to the profile's endpoint/models), an ``.env`` seeded from ~/.hermes/.env with
the resolved ``CARTESIA_BASE_URL`` upserted, the Cartesia plugin symlinked in,
and ``auth.json`` symlinked so the driving LLM reuses existing auth.

Never prints secrets. Internal endpoint hosts are resolved from machine-local
env, never read from or written to committed files.

Usage:
    hermes_agents.py list
    hermes_agents.py resolve <profile>        # JSON, host redacted
    hermes_agents.py materialize <profile>    # prints HERMES_HOME path on stdout
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
PLUGIN_DIR = SCRIPT_DIR / "plugins" / "cartesia"
MAIN_HOME = Path.home() / ".hermes"
# The canonical generic template always lives with the tool.
TEMPLATE_PATH = SCRIPT_DIR / "profiles" / "TEMPLATE.yaml"

# Profiles are loaded from a search PATH so they can live wherever they belong:
# internal/work profiles in the work repo, public ones in the personal/tool
# repos. First match wins on a name collision (like $PATH). Override the whole
# path with HERMES_AGENT_PROFILE_PATH (os.pathsep-separated); otherwise these
# defaults are searched (non-existent dirs are skipped).
_DEFAULT_PROFILE_DIRS = [
    Path.home() / "src" / "karan.hiremath" / "agentic" / "hermes" / "profiles",  # work / internal
    Path.home() / "src" / "hermes" / "profiles",                                 # personal / public
    SCRIPT_DIR / "profiles",                                                     # tooling (TEMPLATE)
]


def profile_path() -> list[Path]:
    raw = os.environ.get("HERMES_AGENT_PROFILE_PATH")
    if raw:
        dirs = [Path(p).expanduser() for p in raw.split(os.pathsep) if p.strip()]
    else:
        dirs = list(_DEFAULT_PROFILE_DIRS)
        legacy = os.environ.get("HERMES_AGENT_PROFILE_DIR")
        if legacy:
            dirs.insert(0, Path(legacy).expanduser())
    seen: set[str] = set()
    out: list[Path] = []
    for d in dirs:
        if not d.exists():
            continue
        key = str(d.resolve())
        if key in seen:
            continue
        seen.add(key)
        out.append(d)
    return out


def _source_label(path: Path) -> str:
    # Match the repo dir specifically — not a bare username substring, since the
    # home dir (/home/karan.hiremath) would make every path look like "work".
    s = str(path)
    if "/src/karan.hiremath/" in s:
        return "work"
    if "/src/hermes/" in s:
        return "personal"
    if "/src/profile/" in s:
        return "profile"
    return path.parent.name


def find_profile(name: str) -> Path:
    for d in profile_path():
        cand = d / f"{name}.yaml"
        if cand.exists():
            return cand
    searched = "\n  ".join(str(d) for d in profile_path()) or "(no profile dirs found)"
    raise SystemExit(f"ERROR: no such profile: {name}. Searched:\n  {searched}")


def _data_home() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "hermes-validation"


def _read_env_file(path: Path) -> Dict[str, str]:
    """Parse a KEY=VALUE .env file. Tolerant: skips blanks/comments."""
    out: Dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        out[key.strip()] = val.strip()
    return out


def _resolve_env(key: str) -> Optional[str]:
    """Resolve an env var from the shell first, then machine-local ~/.hermes/.env."""
    if not key:
        return None
    if os.environ.get(key):
        return os.environ[key]
    return _read_env_file(MAIN_HOME / ".env").get(key)


def load_profile(name: str) -> Dict[str, Any]:
    path = find_profile(name)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise SystemExit(f"ERROR: profile is not a mapping: {path}")
    data.setdefault("name", name)
    return data


def resolve_base_url(profile: Dict[str, Any]) -> str:
    ep = profile.get("endpoint") or {}
    inline = (ep.get("base_url") or "").strip()
    if inline:
        return inline.rstrip("/")
    env_key = (ep.get("base_url_env") or "").strip()
    val = _resolve_env(env_key) if env_key else None
    if not val:
        raise SystemExit(
            f"ERROR: profile '{profile.get('name')}' has no endpoint.base_url and "
            f"env {env_key or '(unset)'} is empty. Set {env_key} in ~/.hermes/.env "
            "(internal hosts stay machine-local)."
        )
    return val.rstrip("/")


def _redact_host(url: str) -> str:
    # Show scheme + a hint, hide the full internal hostname in logs.
    try:
        scheme, _, rest = url.partition("://")
        host = rest.split("/")[0]
        if host in ("api.cartesia.ai",) or host.startswith("localhost") or host.startswith("127."):
            return url  # public / local — fine to show
        parts = host.split(".")
        masked = (parts[0][:3] + "***") if parts else "***"
        return f"{scheme}://{masked}.{'.'.join(parts[1:])}" if len(parts) > 1 else f"{scheme}://{masked}"
    except Exception:
        return "<redacted>"


def _render_config(profile: Dict[str, Any], base_url: str) -> Dict[str, Any]:
    tts = profile.get("tts") or {}
    stt = profile.get("stt") or {}
    llm = profile.get("llm") or {}
    voice = (tts.get("voice") or "").strip() or _resolve_env("CARTESIA_VOICE_ID") or ""
    cfg: Dict[str, Any] = {
        "model": {
            "provider": llm.get("provider", "openai-codex"),
            "default": llm.get("model", "gpt-5.5"),
        },
        "toolsets": profile.get("toolsets") or ["hermes-cli"],
        "plugins": {"enabled": ["cartesia"]},
        "tts": {
            "provider": "cartesia",
            "model": tts.get("model", "sonic-3.5"),
            "voice": voice,
        },
        "stt": {
            "enabled": True,
            "provider": "cartesia",
            "cartesia": {
                "model": stt.get("model", "ink-2"),
                "language": stt.get("language", "en"),
            },
        },
    }
    return cfg


def _upsert_env(path: Path, updates: Dict[str, str]) -> None:
    """Write/refresh .env: seed from ~/.hermes/.env on first create, then upsert
    only the managed keys so manual edits (platform tokens) survive."""
    existing_lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else None
    if existing_lines is None:
        # First create: seed from main .env (CARTESIA_API_KEY + platform tokens).
        seed = MAIN_HOME / ".env"
        existing_lines = seed.read_text(encoding="utf-8").splitlines() if seed.exists() else [
            "# Managed by profile/bin/hermes/agents. Machine-local; do not commit.",
        ]
    keys = set(updates)
    kept = [ln for ln in existing_lines if ln.partition("=")[0].strip() not in keys]
    managed = [f"{k}={v}" for k, v in updates.items() if v]
    path.write_text("\n".join(kept + managed) + "\n", encoding="utf-8")
    path.chmod(0o600)


def materialize(name: str) -> Path:
    profile = load_profile(name)
    base_url = resolve_base_url(profile)
    home = _data_home() / name
    home.mkdir(parents=True, exist_ok=True)
    home.chmod(0o700)

    # config.yaml — always regenerated (fully derived from the profile).
    (home / "config.yaml").write_text(
        yaml.safe_dump(_render_config(profile, base_url), sort_keys=False),
        encoding="utf-8",
    )

    # SOUL.md — persona.
    persona = (profile.get("persona") or "").strip()
    if persona:
        (home / "SOUL.md").write_text(persona + "\n", encoding="utf-8")

    # .env — seed from main once, then upsert managed keys on every run. The
    # API key always re-syncs from ~/.hermes/.env so adding it later propagates;
    # non-managed keys (e.g. gateway platform tokens) are preserved.
    env_updates = {"CARTESIA_BASE_URL": base_url}
    api_key = _resolve_env("CARTESIA_API_KEY")
    if api_key:
        env_updates["CARTESIA_API_KEY"] = api_key
    voice = _render_config(profile, base_url)["tts"]["voice"]
    if voice:
        env_updates["CARTESIA_VOICE_ID"] = voice
    _upsert_env(home / ".env", env_updates)

    # plugin — symlink the canonical profile-repo copy into this home.
    plugins = home / "plugins"
    plugins.mkdir(exist_ok=True)
    link = plugins / "cartesia"
    if link.is_symlink() or link.exists():
        if link.is_symlink():
            link.unlink()
    if not link.exists():
        link.symlink_to(PLUGIN_DIR)

    # auth.json — reuse the operator's LLM auth without re-login.
    main_auth = MAIN_HOME / "auth.json"
    home_auth = home / "auth.json"
    if main_auth.exists() and not home_auth.exists():
        home_auth.symlink_to(main_auth)

    return home


def cmd_list() -> int:
    # Merge across the path; first occurrence of a name wins (shadows later).
    seen: set[str] = set()
    rows = []
    for d in profile_path():
        for p in sorted(d.glob("*.yaml")):
            if p.stem == "TEMPLATE" or p.stem in seen:
                continue
            seen.add(p.stem)
            try:
                prof = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            except Exception:
                continue
            ep = prof.get("endpoint") or {}
            inline = (ep.get("base_url") or "").strip()
            env_key = (ep.get("base_url_env") or "").strip()
            if inline:
                endpoint = inline
            else:
                resolved = _resolve_env(env_key)
                endpoint = _redact_host(resolved) if resolved else f"(unset: {env_key})"
            home = _data_home() / p.stem
            rows.append((
                p.stem, _source_label(d), prof.get("surface", "cli"),
                "ready" if home.exists() else "-", endpoint,
            ))
    w = max([len(r[0]) for r in rows] + [7]) if rows else 7
    print(f"{'PROFILE':<{w}}  {'SOURCE':<8}  {'SURFACE':<8}  {'HOME':<5}  ENDPOINT")
    for name, source, surface, ready, endpoint in rows:
        print(f"{name:<{w}}  {source:<8}  {surface:<8}  {ready:<5}  {endpoint}")
    return 0


def cmd_resolve(name: str) -> int:
    profile = load_profile(name)
    base_url = resolve_base_url(profile)
    cfg = _render_config(profile, base_url)
    out = {
        "name": name,
        "endpoint": _redact_host(base_url),
        "tts_model": cfg["tts"]["model"],
        "stt_model": cfg["stt"]["cartesia"]["model"],
        "voice": "set" if cfg["tts"]["voice"] else "(none)",
        "surface": profile.get("surface", "cli"),
        "platform": profile.get("platform", "telegram"),
        "home": str(_data_home() / name),
    }
    print(json.dumps(out, indent=2))
    return 0


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    cmd, *rest = argv
    if cmd == "list":
        return cmd_list()
    if cmd == "resolve":
        if not rest:
            raise SystemExit("ERROR: resolve needs a profile name")
        return cmd_resolve(rest[0])
    if cmd == "materialize":
        if not rest:
            raise SystemExit("ERROR: materialize needs a profile name")
        print(materialize(rest[0]))
        return 0
    raise SystemExit(f"ERROR: unknown command: {cmd}")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
