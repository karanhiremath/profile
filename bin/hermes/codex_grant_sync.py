#!/usr/bin/env python3
"""Single-writer Codex OAuth grant sync across Hermes, Codex CLI, and Pi.

ChatGPT Codex refresh tokens are single-use. Copying the same grant into
~/.hermes/auth.json, ~/.codex/auth.json, and ~/.pi/agent/auth.json and then
letting each client refresh independently produces token_revoked /
refresh_token_reused. This module keeps one grant, under one lock, and
write-throughs every rotation to every store.

Never prints credential values. Status output is lengths, timestamps, and
boolean match flags only.

Env:
  HERMES_HOME, CODEX_HOME, PI_CODING_AGENT_DIR
  HERMES_CODEX_GRANT_ISOLATE=1   disable write-through
  CODEX_GRANT_LOCK               override lock path
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None  # type: ignore[assignment]


_LOCK_HOLDER = threading.local()


def isolated() -> bool:
    return os.environ.get("HERMES_CODEX_GRANT_ISOLATE", "").strip() == "1"


def _home() -> Path:
    return Path.home()


def hermes_auth_path() -> Path:
    raw = Path(os.environ.get("HERMES_HOME", str(_home() / ".hermes"))).expanduser()
    path = raw / "auth.json"
    if path.exists() or path.is_symlink():
        return path.resolve()
    return path


def cli_auth_path() -> Path:
    raw = os.environ.get("CODEX_HOME", "").strip()
    root = Path(raw).expanduser() if raw else _home() / ".codex"
    path = root / "auth.json"
    if path.exists() or path.is_symlink():
        return path.resolve()
    return path


def pi_auth_path() -> Path:
    raw = os.environ.get("PI_CODING_AGENT_DIR", "").strip()
    root = Path(raw).expanduser() if raw else _home() / ".pi" / "agent"
    path = root / "auth.json"
    if path.exists() or path.is_symlink():
        return path.resolve()
    return path


def grant_lock_path() -> Path:
    override = os.environ.get("CODEX_GRANT_LOCK", "").strip()
    if override:
        return Path(override).expanduser()
    return hermes_auth_path().parent / "codex-grant.lock"


@contextmanager
def grant_lock(timeout_seconds: float = 30.0) -> Iterator[None]:
    depth = getattr(_LOCK_HOLDER, "depth", 0)
    if depth > 0:
        _LOCK_HOLDER.depth = depth + 1
        try:
            yield
        finally:
            _LOCK_HOLDER.depth -= 1
        return

    path = grant_lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if fcntl is None:
        _LOCK_HOLDER.depth = 1
        try:
            yield
        finally:
            _LOCK_HOLDER.depth = 0
        return

    with path.open("a+", encoding="utf-8") as lock_file:
        deadline = time.monotonic() + max(1.0, timeout_seconds)
        while True:
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except (BlockingIOError, OSError):
                if time.monotonic() >= deadline:
                    raise TimeoutError("timed out waiting for Codex grant lock")
                time.sleep(0.05)
        _LOCK_HOLDER.depth = 1
        try:
            yield
        finally:
            _LOCK_HOLDER.depth = 0
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            except (OSError, IOError):
                pass


def _atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2) + "\n"
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, 0o600)
        tmp.replace(path)
        os.chmod(path, 0o600)
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _load_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None
    return raw if isinstance(raw, dict) else None


def _jwt_payload(token: str) -> Dict[str, Any]:
    parts = str(token or "").split(".")
    if len(parts) < 2:
        return {}
    pad = "=" * (-len(parts[1]) % 4)
    try:
        data = json.loads(base64.urlsafe_b64decode(parts[1] + pad))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def access_exp_unix(access_token: str) -> Optional[float]:
    exp = _jwt_payload(access_token).get("exp")
    if isinstance(exp, (int, float)) and exp > 0:
        return float(exp)
    return None


def access_is_expired(access_token: str, now: Optional[float] = None) -> bool:
    exp = access_exp_unix(access_token)
    if exp is None:
        return False
    return exp <= (now if now is not None else time.time())


def parse_last_refresh(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    if isinstance(value, (int, float)):
        numeric = float(value)
        if numeric > 10_000_000_000:
            return numeric / 1000.0
        return numeric
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return 0.0
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return 0.0
    return 0.0


class Grant:
    def __init__(
        self,
        *,
        source: str,
        access_token: str,
        refresh_token: str,
        last_refresh: Any = None,
        account_id: str = "",
        expires_ms: Optional[float] = None,
    ) -> None:
        self.source = source
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.last_refresh = last_refresh
        self.account_id = account_id
        self.expires_ms = expires_ms

    @property
    def usable(self) -> bool:
        return bool(self.access_token.strip() and self.refresh_token.strip())

    def score(self, now: Optional[float] = None) -> tuple:
        now = now if now is not None else time.time()
        expired = access_is_expired(self.access_token, now)
        ts = parse_last_refresh(self.last_refresh)
        if ts <= 0 and self.expires_ms:
            ts = float(self.expires_ms) / 1000.0
        exp = access_exp_unix(self.access_token) or 0.0
        return (0 if expired else 1, ts, exp)

    def as_hermes_tokens(self) -> Dict[str, str]:
        tokens = {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
        }
        if self.account_id:
            tokens["account_id"] = self.account_id
        return tokens


def read_hermes_grant(path: Optional[Path] = None) -> Optional[Grant]:
    payload = _load_json(path or hermes_auth_path())
    if not payload:
        return None
    providers = payload.get("providers")
    state = providers.get("openai-codex") if isinstance(providers, dict) else None
    tokens = state.get("tokens") if isinstance(state, dict) else None
    if not isinstance(tokens, dict):
        return None
    access = str(tokens.get("access_token") or "").strip()
    refresh = str(tokens.get("refresh_token") or "").strip()
    if not access or not refresh:
        return None
    account = str(tokens.get("account_id") or tokens.get("accountId") or "").strip()
    last = state.get("last_refresh") if isinstance(state, dict) else None
    return Grant(
        source="hermes",
        access_token=access,
        refresh_token=refresh,
        last_refresh=last,
        account_id=account,
    )


def read_cli_grant(path: Optional[Path] = None) -> Optional[Grant]:
    payload = _load_json(path or cli_auth_path())
    if not payload:
        return None
    tokens = payload.get("tokens")
    if not isinstance(tokens, dict):
        return None
    access = str(tokens.get("access_token") or "").strip()
    refresh = str(tokens.get("refresh_token") or "").strip()
    if not access or not refresh:
        return None
    account = str(tokens.get("account_id") or tokens.get("accountId") or "").strip()
    return Grant(
        source="cli",
        access_token=access,
        refresh_token=refresh,
        last_refresh=payload.get("last_refresh"),
        account_id=account,
    )


def read_pi_grant(path: Optional[Path] = None) -> Optional[Grant]:
    payload = _load_json(path or pi_auth_path())
    if not payload:
        return None
    cred = payload.get("openai-codex")
    if not isinstance(cred, dict):
        return None
    access = str(cred.get("access") or cred.get("access_token") or "").strip()
    refresh = str(cred.get("refresh") or cred.get("refresh_token") or "").strip()
    if not access or not refresh:
        return None
    expires = cred.get("expires")
    expires_ms = float(expires) if isinstance(expires, (int, float)) else None
    account = str(cred.get("accountId") or cred.get("account_id") or "").strip()
    return Grant(
        source="pi",
        access_token=access,
        refresh_token=refresh,
        last_refresh=expires_ms,
        account_id=account,
        expires_ms=expires_ms,
    )


def collect_grants() -> List[Grant]:
    found: List[Grant] = []
    for reader in (read_hermes_grant, read_cli_grant, read_pi_grant):
        grant = reader()
        if grant and grant.usable:
            found.append(grant)
    return found


def newest_grant(grants: List[Grant]) -> Optional[Grant]:
    usable = [g for g in grants if g.usable]
    if not usable:
        return None
    return max(usable, key=lambda g: g.score())


def _expires_ms_for(grant: Grant) -> int:
    if grant.expires_ms:
        return int(grant.expires_ms)
    exp = access_exp_unix(grant.access_token)
    if exp:
        return int(exp * 1000)
    return int((time.time() + 3600) * 1000)


def write_cli_grant(grant: Grant, path: Optional[Path] = None) -> bool:
    dest = path or cli_auth_path()
    payload = _load_json(dest) or {}
    tokens = dict(payload.get("tokens") or {}) if isinstance(payload.get("tokens"), dict) else {}
    if (
        str(tokens.get("refresh_token") or "") == grant.refresh_token
        and str(tokens.get("access_token") or "") == grant.access_token
    ):
        return False
    tokens["access_token"] = grant.access_token
    tokens["refresh_token"] = grant.refresh_token
    if grant.account_id:
        tokens["account_id"] = grant.account_id
    payload["tokens"] = tokens
    payload["auth_mode"] = payload.get("auth_mode") or "chatgpt"
    if grant.last_refresh:
        payload["last_refresh"] = grant.last_refresh
    else:
        payload["last_refresh"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    _atomic_write_json(dest, payload)
    return True


def write_pi_grant(grant: Grant, path: Optional[Path] = None) -> bool:
    dest = path or pi_auth_path()
    payload = _load_json(dest) or {}
    cred = dict(payload.get("openai-codex") or {}) if isinstance(payload.get("openai-codex"), dict) else {}
    if (
        str(cred.get("refresh") or cred.get("refresh_token") or "") == grant.refresh_token
        and str(cred.get("access") or cred.get("access_token") or "") == grant.access_token
    ):
        return False
    payload["openai-codex"] = {
        "type": "oauth",
        "access": grant.access_token,
        "refresh": grant.refresh_token,
        "expires": _expires_ms_for(grant),
        **({"accountId": grant.account_id} if grant.account_id else {}),
    }
    _atomic_write_json(dest, payload)
    return True


def write_hermes_raw(grant: Grant, path: Optional[Path] = None) -> bool:
    dest = path or hermes_auth_path()
    payload = _load_json(dest) or {"version": 1, "providers": {}}
    providers = payload.get("providers")
    if not isinstance(providers, dict):
        providers = {}
        payload["providers"] = providers
    state = providers.get("openai-codex")
    if not isinstance(state, dict):
        state = {}
    tokens = dict(state.get("tokens") or {}) if isinstance(state.get("tokens"), dict) else {}
    if (
        str(tokens.get("refresh_token") or "") == grant.refresh_token
        and str(tokens.get("access_token") or "") == grant.access_token
    ):
        return False
    previous_access = str(tokens.get("access_token") or "")
    tokens["access_token"] = grant.access_token
    tokens["refresh_token"] = grant.refresh_token
    if grant.account_id:
        tokens["account_id"] = grant.account_id
    state["tokens"] = tokens
    state["auth_mode"] = "chatgpt"
    state["last_refresh"] = grant.last_refresh or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    providers["openai-codex"] = state
    pool = payload.get("credential_pool")
    if isinstance(pool, dict):
        entries = pool.get("openai-codex")
        if isinstance(entries, list):
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                source = entry.get("source")
                if source == "device_code" or (
                    source == "manual:device_code"
                    and previous_access
                    and entry.get("access_token") == previous_access
                ):
                    entry["access_token"] = grant.access_token
                    entry["refresh_token"] = grant.refresh_token
                    entry["last_refresh"] = state["last_refresh"]
                    entry["last_status"] = None
                    entry["last_error_code"] = None
                    entry["last_error_reason"] = None
                    entry["last_error_message"] = None
    _atomic_write_json(dest, payload)
    return True


def export_peers(grant: Grant) -> List[str]:
    if isolated():
        return []
    wrote: List[str] = []
    if write_cli_grant(grant):
        wrote.append("cli")
    if write_pi_grant(grant):
        wrote.append("pi")
    return wrote


def adopt_newest(*, write_hermes: bool = True) -> Dict[str, Any]:
    """Align every store to the newest usable grant. No HTTP refresh."""
    with grant_lock():
        grants = collect_grants()
        chosen = newest_grant(grants)
        if chosen is None:
            return {"status": "empty", "wrote": []}
        wrote: List[str] = []
        if write_hermes and write_hermes_raw(chosen):
            wrote.append("hermes")
        wrote.extend(export_peers(chosen))
        return {
            "status": "ok",
            "source": chosen.source,
            "wrote": wrote,
            "stores": len(grants),
            "refresh_aligned": _refresh_aligned(),
        }


def _refresh_aligned() -> bool:
    grants = [g for g in collect_grants() if g.usable]
    if len(grants) < 2:
        return True
    first = grants[0].refresh_token
    return all(g.refresh_token == first for g in grants)


def adopt_if_peer_newer(tokens: Dict[str, str]) -> Optional[Grant]:
    """If a peer store already rotated this grant, return that grant."""
    current_refresh = str(tokens.get("refresh_token") or "").strip()
    if not current_refresh or isolated():
        return None
    with grant_lock():
        grants = collect_grants()
        chosen = newest_grant(grants)
        if chosen is None:
            return None
        if chosen.refresh_token == current_refresh:
            return None
        write_hermes_raw(chosen)
        export_peers(chosen)
        return chosen


def status_report() -> Dict[str, Any]:
    hermes = read_hermes_grant()
    cli = read_cli_grant()
    pi = read_pi_grant()
    grants = [g for g in (hermes, cli, pi) if g]
    chosen = newest_grant(grants)
    report = {
        "hermes_present": bool(hermes),
        "cli_present": bool(cli),
        "pi_present": bool(pi),
        "hermes_access_len": len(hermes.access_token) if hermes else 0,
        "cli_access_len": len(cli.access_token) if cli else 0,
        "pi_access_len": len(pi.access_token) if pi else 0,
        "hermes_refresh_len": len(hermes.refresh_token) if hermes else 0,
        "cli_refresh_len": len(cli.refresh_token) if cli else 0,
        "pi_refresh_len": len(pi.refresh_token) if pi else 0,
        "hermes_refresh_matches_cli": bool(
            hermes and cli and hermes.refresh_token == cli.refresh_token
        ),
        "hermes_refresh_matches_pi": bool(
            hermes and pi and hermes.refresh_token == pi.refresh_token
        ),
        "cli_refresh_matches_pi": bool(
            cli and pi and cli.refresh_token == pi.refresh_token
        ),
        "refresh_aligned": _refresh_aligned() if grants else True,
        "newest_source": chosen.source if chosen else "",
        "isolated": isolated(),
        "hermes_auth": str(hermes_auth_path()),
        "cli_auth": str(cli_auth_path()),
        "pi_auth": str(pi_auth_path()),
        "lock": str(grant_lock_path()),
    }
    return report


def install_into_hermes_auth(auth: Any) -> None:
    """Wrap Hermes save/refresh so every rotation write-throughs peers."""
    if getattr(auth, "_codex_grant_sync_installed", False) is True:
        return

    orig_save = auth._save_codex_tokens
    orig_refresh = auth._refresh_codex_auth_tokens
    orig_recover = auth._recover_codex_tokens_from_cli

    def save(tokens, last_refresh=None, label=None):
        orig_save(tokens, last_refresh, label)
        if isolated():
            return
        grant = Grant(
            source="hermes",
            access_token=str(tokens.get("access_token") or ""),
            refresh_token=str(tokens.get("refresh_token") or ""),
            last_refresh=last_refresh,
            account_id=str(tokens.get("account_id") or tokens.get("accountId") or ""),
        )
        if grant.usable:
            with grant_lock():
                export_peers(grant)

    def recover(reason: str):
        imported = orig_recover(reason)
        if imported:
            return imported
        pi = read_pi_grant()
        if not (pi and pi.usable):
            return None
        if access_is_expired(pi.access_token):
            return None
        orig_save(pi.as_hermes_tokens(), label="adopted-from-pi")
        return pi.as_hermes_tokens()

    def refresh(tokens, timeout_seconds):
        with grant_lock():
            adopted = adopt_if_peer_newer(tokens)
            if adopted is not None:
                tokens = adopted.as_hermes_tokens()
                exp = access_exp_unix(adopted.access_token)
                skew = getattr(auth, "CODEX_ACCESS_TOKEN_REFRESH_SKEW_SECONDS", 120)
                if exp is None or exp > time.time() + float(skew):
                    return tokens
            return orig_refresh(tokens, timeout_seconds)

    auth._save_codex_tokens = save
    auth._recover_codex_tokens_from_cli = recover
    auth._refresh_codex_auth_tokens = refresh
    auth._codex_grant_sync_installed = True


def _print_status(report: Dict[str, Any]) -> None:
    for key in sorted(report):
        value = report[key]
        if isinstance(value, bool):
            shown = "true" if value else "false"
        elif isinstance(value, list):
            shown = ",".join(str(item) for item in value)
        else:
            shown = str(value)
        print(f"{key}={shown}")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Align Codex OAuth grants without printing secrets.")
    parser.add_argument(
        "command",
        choices=("status", "adopt"),
        help="status: boolean/length report. adopt: write-through newest grant to all stores.",
    )
    args = parser.parse_args(argv)
    if args.command == "status":
        _print_status(status_report())
        return 0
    result = adopt_newest()
    print(f"status={result['status']}")
    print(f"source={result.get('source', '')}")
    print(f"wrote={','.join(result.get('wrote') or [])}")
    print(f"stores={result.get('stores', 0)}")
    print(f"refresh_aligned={str(result.get('refresh_aligned', True)).lower()}")
    return 0 if result["status"] in {"ok", "empty"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
