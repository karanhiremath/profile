#!/usr/bin/env python3
"""Backend for the `agents` launcher: resolve an agent profile and materialize
an isolated HERMES_HOME for it.

Each agent gets its own HERMES_HOME under
``$XDG_DATA_HOME/hermes-agents/<name>/`` so it never touches the operator's
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
    hermes_agents.py secrets-status           # cache presence only; never the key
    hermes_agents.py secrets-refresh          # pull from 1Password once, then cache
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

# Cursor SDK reads process env CURSOR_API_KEY. Default op account on this
# machine is personal; the Employee item lives on cartesia.1password.com.
_DEFAULT_CURSOR_OP_ACCOUNT = "cartesia.1password.com"
_DEFAULT_CURSOR_OP_REF = "op://Employee/Cursor pi-coding-agent/credential"
_DEFAULT_CURSOR_OP_FALLBACK_REF = "op://Personal/Cursor pi-coding-agent/credential"

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


def _apply_host_env() -> None:
    """Load class-gated Hermes paths unless the operator already exported them."""
    if os.environ.get("HERMES_AGENT_PROFILE_PATH") and os.environ.get("AGENTIC_HOST_CLASS"):
        return
    script = Path(__file__).resolve().parent.parent / "agentic-dev" / "host-env.sh"
    if not script.is_file():
        return
    try:
        raw = subprocess.check_output(["bash", str(script), "--json"], text=True)
        data = json.loads(raw)
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError):
        return
    os.environ.setdefault("AGENTIC_HOST_CLASS", str(data.get("class") or ""))
    os.environ.setdefault("AGENTIC_COSW_PLANE", str(data.get("plane") or ""))
    os.environ.setdefault("HERMES_AGENT_PROFILE_PATH", str(data.get("HERMES_AGENT_PROFILE_PATH") or ""))
    os.environ.setdefault(
        "HERMES_PROJECT_REGISTRY_PATH", str(data.get("HERMES_PROJECT_REGISTRY_PATH") or "")
    )
    os.environ.setdefault(
        "HERMES_PROJECT_REGISTRY_DIRS",
        os.environ.get("HERMES_PROJECT_REGISTRY_PATH", ""),
    )


_apply_host_env()


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
    if override := os.environ.get("HERMES_AGENTS_DATA_HOME"):
        return Path(override).expanduser()
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "hermes-agents"


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


def _cursor_api_key_from_pi_auth() -> Optional[str]:
    """Read the Cursor key Pi already stores, without printing it."""
    raw_dir = os.environ.get("PI_AGENT_DIR") or str(Path.home() / ".pi" / "agent")
    path = Path(raw_dir).expanduser() / "auth.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    cursor = data.get("cursor")
    if not isinstance(cursor, dict):
        return None
    key = str(cursor.get("key") or cursor.get("api_key") or "").strip()
    return key or None


def _personal_host() -> bool:
    """Mini / personal machines have no work checkout and no Cartesia 1P."""
    return not (Path.home() / "src" / "karan.hiremath").exists()


def cursor_op_candidates() -> List[Tuple[str, str]]:
    """(account, op://ref) pairs. Empty account uses op's default account."""
    if _personal_host() and "HERMES_CURSOR_OP_ACCOUNT" not in os.environ:
        account = ""
        ref = os.environ.get(
            "HERMES_CURSOR_OP_REF", _DEFAULT_CURSOR_OP_FALLBACK_REF
        ).strip()
        return [(account, ref)]
    account = os.environ.get("HERMES_CURSOR_OP_ACCOUNT", _DEFAULT_CURSOR_OP_ACCOUNT).strip()
    ref = os.environ.get("HERMES_CURSOR_OP_REF", _DEFAULT_CURSOR_OP_REF).strip()
    fallback = os.environ.get(
        "HERMES_CURSOR_OP_FALLBACK_REF", _DEFAULT_CURSOR_OP_FALLBACK_REF
    ).strip()
    out: List[Tuple[str, str]] = [(account, ref)]
    if fallback and fallback != ref:
        out.append(("", fallback))
    return out


_CURSOR_KEYCHAIN_SERVICE = "hermes.cursor-api-key"
_SECRETS_DIR = Path.home() / ".local" / "share" / "hermes-secrets"
_CURSOR_META = _SECRETS_DIR / "cursor.meta.json"


def _secrets_refresh_requested() -> bool:
    return os.environ.get("HERMES_SECRETS_REFRESH", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "refresh",
    }


def cursor_onepassword_secrets() -> Dict[str, Any]:
    """Hermes must not call `op` at TUI start. Stage via keychain / .env instead."""
    return {"onepassword": {"enabled": False}}


def _cursor_sdk_model(model: str) -> str:
    """Keep Cursor thinking suffixes such as :fast.

    Mini used to reject grok-4.6:fast; the timeout-free Cursor SDK overlay
    accepts it. Do not strip the suffix here or Cos/Cosw rematerialize to
    grok-4.6 and lose the intended seat.
    """
    return model


def _write_cursor_meta(*, source: str, backend: str) -> None:
    _SECRETS_DIR.mkdir(parents=True, exist_ok=True)
    _SECRETS_DIR.chmod(0o700)
    payload = {
        "service": _CURSOR_KEYCHAIN_SERVICE,
        "updated": __import__("datetime").datetime.now().astimezone().isoformat(timespec="seconds"),
        "source": source,
        "backend": backend,
    }
    _CURSOR_META.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    _CURSOR_META.chmod(0o600)


def _keychain_get_cursor_key() -> Optional[str]:
    if sys.platform != "darwin":
        return None
    try:
        proc = subprocess.run(
            [
                "security",
                "find-generic-password",
                "-s",
                _CURSOR_KEYCHAIN_SERVICE,
                "-a",
                os.environ.get("USER") or os.environ.get("LOGNAME") or "",
                "-w",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    key = (proc.stdout or "").strip()
    return key if proc.returncode == 0 and key else None


def _keychain_set_cursor_key(key: str) -> bool:
    if sys.platform != "darwin" or not key:
        return False
    account = os.environ.get("USER") or os.environ.get("LOGNAME") or ""
    try:
        subprocess.run(
            [
                "security",
                "add-generic-password",
                "-U",
                "-s",
                _CURSOR_KEYCHAIN_SERVICE,
                "-a",
                account,
                "-w",
                key,
                "-T",
                "/usr/bin/security",
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return _keychain_get_cursor_key() == key


def _file_cache_path() -> Path:
    return _SECRETS_DIR / "cursor-api-key"


def _file_cache_get() -> Optional[str]:
    path = _file_cache_path()
    if not path.exists():
        return None
    key = path.read_text(encoding="utf-8").strip()
    return key or None


def _file_cache_set(key: str) -> None:
    _SECRETS_DIR.mkdir(parents=True, exist_ok=True)
    _SECRETS_DIR.chmod(0o700)
    path = _file_cache_path()
    path.write_text(key + "\n", encoding="utf-8")
    path.chmod(0o600)


def _stage_cursor_secret(key: str, *, source: str) -> None:
    """Persist to 0600 file. Keychain only on explicit 1Password refresh."""
    if not key:
        return
    if _file_cache_get() != key:
        _file_cache_set(key)
    backend = "file"
    if source == "onepassword" and _keychain_get_cursor_key() != key:
        if _keychain_set_cursor_key(key):
            backend = "keychain"
    _stage_cursor_key_slots(key)
    if not _CURSOR_META.exists() or source == "onepassword":
        _write_cursor_meta(source=source, backend=backend)


def _cursor_api_key_from_op() -> Optional[str]:
    """1Password only on cache miss or explicit refresh. Never prints the value."""
    for account, ref in cursor_op_candidates():
        cmd = ["op", "read"]
        if account:
            cmd.extend(["--account", account])
        cmd.extend(["--", ref])
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=20, check=False
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        key = (proc.stdout or "").strip()
        if proc.returncode == 0 and key:
            return key
    return None


def _resolve_cursor_api_key() -> Optional[str]:
    """Frictionless path: env → file cache → dotenv → pi → keychain. `op` last."""
    if os.environ.get("CURSOR_API_KEY"):
        return os.environ["CURSOR_API_KEY"]
    refresh = _secrets_refresh_requested()
    if not refresh:
        cached = _file_cache_get()
        if cached:
            return cached
        from_dotenv = _read_env_file(MAIN_HOME / ".env").get("CURSOR_API_KEY")
        if from_dotenv:
            _stage_cursor_secret(from_dotenv, source="dotenv")
            return from_dotenv
        from_pi = _cursor_api_key_from_pi_auth()
        if from_pi:
            _stage_cursor_secret(from_pi, source="pi-auth")
            return from_pi
        cached_kc = _keychain_get_cursor_key()
        if cached_kc:
            _file_cache_set(cached_kc)
            _write_cursor_meta(source="keychain", backend="keychain")
            return cached_kc
    key = _cursor_api_key_from_op()
    if key:
        _stage_cursor_secret(key, source="onepassword")
        return key
    if refresh:
        cached = _keychain_get_cursor_key() or _file_cache_get()
        if cached:
            return cached
    return None


def _resolve_env(key: str) -> Optional[str]:
    """Resolve an env var from the shell first, then machine-local ~/.hermes/.env."""
    if not key:
        return None
    if key == "CURSOR_API_KEY":
        return _resolve_cursor_api_key()
    if os.environ.get(key):
        return os.environ[key]
    return _read_env_file(MAIN_HOME / ".env").get(key)


def _stage_cursor_key_slots(key: str) -> None:
    """Write the Cursor key to the slots Hermes / cursor-agent actually read."""
    if not key:
        return
    _upsert_env(MAIN_HOME / ".env", {"CURSOR_API_KEY": key})
    agent_env = Path.home() / ".cursor" / "agent.env"
    agent_env.parent.mkdir(parents=True, exist_ok=True)
    existing = _read_env_file(agent_env)
    existing["CURSOR_API_KEY"] = key
    lines = [f"{k}={v}" for k, v in existing.items() if v]
    agent_env.write_text("\n".join(lines) + "\n", encoding="utf-8")
    agent_env.chmod(0o600)


def load_profile(name: str) -> Dict[str, Any]:
    path = find_profile(name)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise SystemExit(f"ERROR: profile is not a mapping: {path}")
    data.setdefault("name", name)
    return data


def voice_on(profile: Dict[str, Any]) -> bool:
    """Whether this agent uses TTS/STT at all. Text-only agents (tts+stt both
    disabled) need no Cartesia endpoint and skip all voice wiring."""
    tts = profile.get("tts") or {}
    stt = profile.get("stt") or {}
    return bool(tts.get("enabled", True)) or bool(stt.get("enabled", True))


def resolve_base_url(profile: Dict[str, Any], *, required: bool = True) -> Optional[str]:
    ep = profile.get("endpoint") or {}
    inline = (ep.get("base_url") or "").strip()
    if inline:
        return inline.rstrip("/")
    env_key = (ep.get("base_url_env") or "").strip()
    val = _resolve_env(env_key) if env_key else None
    if not val:
        if not required:
            return None
        raise SystemExit(
            f"ERROR: profile '{profile.get('name')}' has no endpoint.base_url and "
            f"env {env_key or '(unset)'} is empty. Set {env_key} in ~/.hermes/.env "
            "(internal hosts stay machine-local), or set tts.enabled+stt.enabled "
            "to false for a text-only agent."
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


def terminal_backend_override() -> str:
    """Launcher override. HERMES_AGENT_TERMINAL_BACKEND wins over TERMINAL_ENV."""
    return (
        os.environ.get("HERMES_AGENT_TERMINAL_BACKEND", "").strip()
        or os.environ.get("TERMINAL_ENV", "").strip()
    )


def _parse_docker_volumes(raw: str) -> list[str]:
    raw = raw.strip()
    if not raw:
        return []
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError:
        return [item.strip() for item in raw.split(",") if item.strip()]
    if isinstance(loaded, list) and all(isinstance(item, str) for item in loaded):
        return loaded
    return []


def apply_docker_terminal(terminal: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Fill docker terminal fields from env so profile YAML and launchers compose."""
    out = dict(terminal) if isinstance(terminal, dict) else {}
    out["backend"] = "docker"
    if not out.get("cwd"):
        out["cwd"] = os.environ.get("TERMINAL_CWD", "").strip() or "/root"
    out.setdefault(
        "docker_image",
        os.environ.get("TERMINAL_DOCKER_IMAGE", "").strip() or "localhost/hermes-agent/python-node:dev",
    )
    volumes_env = os.environ.get("TERMINAL_DOCKER_VOLUMES", "")
    volumes = _parse_docker_volumes(volumes_env)
    if volumes:
        out["docker_volumes"] = volumes
    src = Path.home() / "src"
    if src.is_dir() and not out.get("docker_volumes"):
        out["docker_volumes"] = [f"{src}:/root/src", f"{src}:/home/hermes/src"]
    persist = os.environ.get("TERMINAL_DOCKER_PERSIST_ACROSS_PROCESSES", "").strip()
    if persist:
        out["docker_persist_across_processes"] = persist.lower() in {"1", "true", "yes"}
    else:
        out.setdefault("docker_persist_across_processes", False)
    return out


def resolve_terminal(profile: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve Hermes terminal backend from profile YAML plus launcher env.

    Host-vs-sandbox used to drift because launchers set TERMINAL_ENV while
    materialize only honored HERMES_AGENT_TERMINAL_BACKEND, and docker
    volumes were applied only on that override path.
    """
    terminal = profile.get("terminal")
    terminal = dict(terminal) if isinstance(terminal, dict) else {}
    override = terminal_backend_override()
    if override == "local":
        return {"backend": "local"}
    if override == "docker":
        return apply_docker_terminal(terminal)
    if override in {"singularity", "modal", "daytona"}:
        terminal["backend"] = override
        if not terminal.get("cwd"):
            terminal["cwd"] = "/root"
        return terminal
    if terminal.get("backend") == "docker":
        return apply_docker_terminal(terminal)
    return terminal


def terminal_env_updates(terminal_cfg: Dict[str, Any]) -> Dict[str, str]:
    """Always persist TERMINAL_ENV so a prior host-tools launch cannot stick."""
    backend = str(terminal_cfg.get("backend") or "").strip()
    if backend == "docker":
        updates = {
            "TERMINAL_ENV": "docker",
            "TERMINAL_CWD": str(terminal_cfg.get("cwd") or "/root"),
        }
        if terminal_cfg.get("docker_image"):
            updates["TERMINAL_DOCKER_IMAGE"] = str(terminal_cfg["docker_image"])
        if terminal_cfg.get("docker_volumes"):
            updates["TERMINAL_DOCKER_VOLUMES"] = json.dumps(terminal_cfg["docker_volumes"])
        if "docker_persist_across_processes" in terminal_cfg:
            updates["TERMINAL_DOCKER_PERSIST_ACROSS_PROCESSES"] = (
                "true" if terminal_cfg["docker_persist_across_processes"] else "false"
            )
        docker_bin = os.environ.get("HERMES_DOCKER_BINARY", "").strip()
        if docker_bin:
            updates["HERMES_DOCKER_BINARY"] = docker_bin
        return updates
    if backend == "local":
        return {"TERMINAL_ENV": "local"}
    return {}


def llm_from_profile(profile: Dict[str, Any]) -> Dict[str, Any]:
    """Profile YAML seat, with launch-scoped env overrides from `cos --codex`."""
    llm = dict(profile.get("llm") or {})
    provider = os.environ.get("HERMES_AGENT_LLM_PROVIDER", "").strip()
    model = os.environ.get("HERMES_AGENT_LLM_MODEL", "").strip()
    if provider:
        llm["provider"] = provider
    if model:
        llm["model"] = model
    return llm


def _render_config(profile: Dict[str, Any]) -> Dict[str, Any]:
    tts = profile.get("tts") or {}
    stt = profile.get("stt") or {}
    llm = llm_from_profile(profile)
    tts_on = bool(tts.get("enabled", True))
    stt_on = bool(stt.get("enabled", True))
    voice = (tts.get("voice") or "").strip() or _resolve_env("CARTESIA_VOICE_ID") or ""

    toolsets = list(profile.get("toolsets") or ["hermes-cli"])
    if not tts_on and "tts" in toolsets:
        toolsets.remove("tts")

    cfg: Dict[str, Any] = {
        "model": {
            "provider": llm.get("provider", "openai-codex"),
            "default": _cursor_sdk_model(str(llm.get("model", "gpt-5.5"))),
        },
        "toolsets": toolsets,
        "plugins": {"enabled": ["cartesia"] if (tts_on or stt_on) else []},
    }
    display = profile.get("display")
    if isinstance(display, dict) and display:
        cfg["display"] = display
    terminal = resolve_terminal(profile)
    if terminal:
        cfg["terminal"] = terminal
    if tts_on:
        cfg["tts"] = {"provider": "cartesia", "model": tts.get("model", "sonic-3.5"), "voice": voice}
    if stt_on:
        cfg["stt"] = {
            "enabled": True,
            "provider": "cartesia",
            "cartesia": {"model": stt.get("model", "ink-2"), "language": stt.get("language", "en")},
        }
    else:
        cfg["stt"] = {"enabled": False}
    cfg["secrets"] = cursor_onepassword_secrets()
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


def _force_config() -> bool:
    return os.environ.get("HERMES_AGENT_FORCE_CONFIG", "").strip() in {"1", "true", "yes"}


def _merge_json_file(path: Path, updates: Dict[str, Any], *, force: bool = False) -> None:
    """Merge top-level JSON preferences, preserving unrelated Herm TUI state.

    Theme pins (`nighttideDefault`) and an already-written theme survive YAML
    rematerialize unless HERMES_AGENT_FORCE_CONFIG=1 or force=True.
    """
    existing: Dict[str, Any] = {}
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                existing = loaded
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            existing = {}
    pinned = existing.get("nighttideDefault")
    protect_theme = bool(pinned or existing.get("theme")) and not force
    merged = dict(existing)
    for key, value in updates.items():
        if protect_theme and key in {"theme", "themeMode"}:
            continue
        merged[key] = value
    if protect_theme and pinned and not merged.get("theme"):
        merged["theme"] = pinned
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")


def _merge_existing_config(path: Path, cfg: Dict[str, Any], *, force: bool = False) -> Dict[str, Any]:
    """Keep TUI-owned config.yaml keys across agents-up rematerialize."""
    if force or not path.exists():
        return cfg
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        return cfg
    if not isinstance(loaded, dict):
        return cfg
    out = dict(cfg)
    for key in ("toolsets", "display"):
        if key in loaded:
            out[key] = loaded[key]
    model = loaded.get("model")
    if isinstance(model, dict) and model.get("default"):
        out.setdefault("model", {})
        if isinstance(out["model"], dict):
            out["model"] = dict(out["model"])
            out["model"]["default"] = model["default"]
            if model.get("provider"):
                out["model"]["provider"] = model["provider"]
    return out


def _link_skill_tree(dest: Path, src: Path) -> None:
    if not src.exists():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_symlink() or dest.is_file():
        try:
            dest.unlink()
        except FileNotFoundError:
            pass
    if dest.exists() and not dest.is_symlink():
        return
    try:
        dest.symlink_to(src)
    except FileExistsError:
        return


def _link_autonomous_family(dest: Path, *src_roots: Path) -> None:
    """Real dir of per-skill links so optional grok sits beside bundled names."""
    if dest.is_symlink() or dest.is_file():
        try:
            dest.unlink()
        except FileNotFoundError:
            pass
    dest.mkdir(parents=True, exist_ok=True)
    for src_root in src_roots:
        if not src_root.is_dir():
            continue
        for child in sorted(src_root.iterdir()):
            if child.is_dir() and (child / "SKILL.md").exists():
                _link_skill_tree(dest / child.name, child)


def _ensure_skill_links(home: Path) -> None:
    """Point isolated HERMES_HOME skills at Hermes official + profile trees."""
    skills = home / "skills"
    skills.mkdir(parents=True, exist_ok=True)
    hermes_root = Path.home() / "src" / "hermes-agent"
    bundled = hermes_root / "skills" / "autonomous-ai-agents"
    optional = hermes_root / "optional-skills" / "autonomous-ai-agents"
    _link_autonomous_family(skills / "autonomous-ai-agents", bundled, optional)
    profile_skills = SCRIPT_DIR.parent.parent / "skills" / "pi"
    if profile_skills.is_dir():
        for child in sorted(profile_skills.iterdir()):
            if child.is_dir() and (child / "SKILL.md").exists():
                _link_skill_tree(skills / child.name, child)
    shared = SCRIPT_DIR.parent.parent / "skills" / "shared"
    if shared.is_dir():
        for child in sorted(shared.iterdir()):
            if child.is_dir() and (child / "SKILL.md").exists():
                _link_skill_tree(skills / child.name, child)


def _ensure_cartesia_plugin(home: Path) -> None:
    plugins = home / "plugins"
    plugins.mkdir(exist_ok=True)
    link = plugins / "cartesia"
    try:
        if link.is_symlink() and link.resolve() == PLUGIN_DIR.resolve():
            return
    except OSError:
        pass
    if link.is_symlink() or link.is_file():
        try:
            link.unlink()
        except FileNotFoundError:
            pass
    if link.exists():
        return
    try:
        link.symlink_to(PLUGIN_DIR)
    except FileExistsError:
        return


def materialize(name: str) -> Path:
    profile = load_profile(name)
    uses_voice = voice_on(profile)
    base_url = resolve_base_url(profile, required=uses_voice)
    home = _data_home() / name
    home.mkdir(parents=True, exist_ok=True)
    home.chmod(0o700)

    force_cfg = _force_config()
    cfg = _render_config(profile)
    cfg = _merge_existing_config(home / "config.yaml", cfg, force=force_cfg)
    herm_prefs = (profile.get("herm") or {}).get("preferences") or {}
    if not isinstance(herm_prefs, dict):
        herm_prefs = {}
    # config.yaml — profile defaults, then TUI-owned keys unless forced.
    (home / "config.yaml").write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
    if herm_prefs:
        _merge_json_file(home / "herm" / "tui.json", herm_prefs, force=force_cfg)
    _ensure_skill_links(home)

    # SOUL.md — persona.
    persona = (profile.get("persona") or "").strip()
    if persona:
        (home / "SOUL.md").write_text(persona + "\n", encoding="utf-8")

    # .env — seed from main once, then upsert managed keys on every run. The
    # API key always re-syncs from ~/.hermes/.env so adding it later propagates;
    # non-managed keys (e.g. gateway platform tokens) are preserved. Voice keys
    # are written only for voice-enabled agents.
    env_updates: Dict[str, str] = {}
    env_updates.update(terminal_env_updates(cfg.get("terminal") if isinstance(cfg.get("terminal"), dict) else {}))
    if uses_voice:
        if base_url:
            env_updates["CARTESIA_BASE_URL"] = base_url
        api_key = _resolve_env("CARTESIA_API_KEY")
        if api_key:
            env_updates["CARTESIA_API_KEY"] = api_key
        voice = cfg.get("tts", {}).get("voice")
        if voice:
            env_updates["CARTESIA_VOICE_ID"] = voice
    cursor_key = _resolve_env("CURSOR_API_KEY")
    if cursor_key:
        env_updates["CURSOR_API_KEY"] = cursor_key
    _upsert_env(home / ".env", env_updates)

    def sync_runtime_home(runtime_home: Path) -> None:
        """Mirror the materialized config into a real Hermes named profile.

        Hermes reports the active profile as `default` whenever HERMES_HOME is a
        custom root. Pointing launches at <root>/profiles/<name> makes the
        startup metadata and prompt symbol show the agent profile name.
        """
        runtime_home.mkdir(parents=True, exist_ok=True)
        runtime_home.chmod(0o700)
        runtime_cfg = _merge_existing_config(runtime_home / "config.yaml", cfg, force=force_cfg)
        (runtime_home / "config.yaml").write_text(yaml.safe_dump(runtime_cfg, sort_keys=False), encoding="utf-8")
        if herm_prefs:
            _merge_json_file(runtime_home / "herm" / "tui.json", herm_prefs, force=force_cfg)
        _ensure_skill_links(runtime_home)
        if persona:
            (runtime_home / "SOUL.md").write_text(persona + "\n", encoding="utf-8")
        _upsert_env(runtime_home / ".env", env_updates)

        if uses_voice:
            _ensure_cartesia_plugin(runtime_home)

        main_auth = MAIN_HOME / "auth.json"
        runtime_auth = runtime_home / "auth.json"
        if main_auth.exists() and not runtime_auth.exists():
            runtime_auth.symlink_to(main_auth)

    # plugin — symlink the canonical profile-repo copy into this home (only when
    # the agent actually uses voice).
    if uses_voice:
        _ensure_cartesia_plugin(home)

    # auth.json — reuse the operator's LLM auth without re-login.
    main_auth = MAIN_HOME / "auth.json"
    home_auth = home / "auth.json"
    if main_auth.exists() and not home_auth.exists():
        home_auth.symlink_to(main_auth)

    # Make the agent's own name a real Hermes named profile inside the isolated
    # root, and mark it active for humans inspecting the root with profile list.
    runtime_name = str(profile.get("runtime_profile") or name).strip() or name
    runtime_home = home / "profiles" / runtime_name
    sync_runtime_home(runtime_home)
    (home / "active_profile").write_text(runtime_name + "\n", encoding="utf-8")

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
            if not voice_on(prof):
                endpoint = "(text-only)"
            else:
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
    uses_voice = voice_on(profile)
    cfg = _render_config(profile)
    out: Dict[str, Any] = {
        "name": name,
        "voice": uses_voice,
        "surface": profile.get("surface", "cli"),
        "platform": profile.get("platform", "telegram"),
        "toolsets": cfg["toolsets"],
        "home": str(_data_home() / name),
    }
    if uses_voice:
        base_url = resolve_base_url(profile, required=False)
        out["endpoint"] = _redact_host(base_url) if base_url else "(unset)"
        if "tts" in cfg:
            out["tts_model"] = cfg["tts"]["model"]
            out["tts_voice"] = "set" if cfg["tts"]["voice"] else "(none)"
        if cfg.get("stt", {}).get("enabled"):
            out["stt_model"] = cfg["stt"]["cartesia"]["model"]
    else:
        out["endpoint"] = "(text-only)"
    terminal = cfg.get("terminal") if isinstance(cfg.get("terminal"), dict) else {}
    out["terminal_backend"] = terminal.get("backend") or "unset"
    if terminal.get("docker_image"):
        out["terminal_image"] = terminal["docker_image"]
    print(json.dumps(out, indent=2))
    return 0


def cmd_secrets_status() -> int:
    """Non-secret status only. Never prints credential material."""
    meta: Dict[str, Any] = {}
    if _CURSOR_META.exists():
        try:
            loaded = json.loads(_CURSOR_META.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                meta = loaded
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            meta = {}
    has_keychain = bool(_keychain_get_cursor_key())
    has_file = bool(_file_cache_get())
    has_dotenv = bool(_read_env_file(MAIN_HOME / ".env").get("CURSOR_API_KEY"))
    has_pi = bool(_cursor_api_key_from_pi_auth())
    print(f"onepassword_runtime=disabled")
    print(f"keychain={'present' if has_keychain else 'missing'}")
    print(f"file_cache={'present' if has_file else 'missing'}")
    print(f"hermes_dotenv={'present' if has_dotenv else 'missing'}")
    print(f"pi_auth={'present' if has_pi else 'missing'}")
    print(f"cached_source={meta.get('source', 'unknown')}")
    print(f"cached_backend={meta.get('backend', 'unknown')}")
    print(f"cached_updated={meta.get('updated', 'unknown')}")
    return 0


def cmd_secrets_refresh() -> int:
    os.environ["HERMES_SECRETS_REFRESH"] = "1"
    key = _resolve_cursor_api_key()
    if not key:
        print("cursor_key=missing", file=sys.stderr)
        return 1
    print("cursor_key=staged")
    return cmd_secrets_status()


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
    if cmd == "secrets-status":
        return cmd_secrets_status()
    if cmd == "secrets-refresh":
        return cmd_secrets_refresh()
    raise SystemExit(f"ERROR: unknown command: {cmd}")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
