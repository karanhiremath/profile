"""Official Perplexity API + MCP detection. No undocumented REST, no cookies."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

API_BASE = "https://api.perplexity.ai"
AGENT_URL = f"{API_BASE}/v1/agent"
SONAR_URL = f"{API_BASE}/v1/sonar"
SEARCH_URL = f"{API_BASE}/search"
MODELS_URL = f"{API_BASE}/v1/models"
MCP_REMOTE = "https://api.perplexity.ai/mcp"
MCP_DOCS = "https://docs.perplexity.ai/mcp"
CURSOR_MCP = Path.home() / ".cursor" / "mcp.json"
STATE = Path(os.environ.get("PI_PERPLEXITY_STATE", Path.home() / ".local/share/pi-perplexity"))
USAGE_LOG = STATE / "api-usage.jsonl"

# Conservative local cap until the account's tier is known.
# Official Agent API Tier 0 is 50 RPM / 1 QPS:
# https://docs.perplexity.ai/docs/admin/rate-limits-usage-tiers
DEFAULT_RPM = 20
COOLDOWN_PATH = STATE / "api-cooldown.json"

PRESETS = {"low", "medium", "high", "fast", "xhigh"}
OFFICIAL_LIMITS = {
    "source": "https://docs.perplexity.ai/docs/admin/rate-limits-usage-tiers",
    "account_tier": "unknown",
    "agent_tier0": {"qps": 1, "rpm": 50},
    "search": {
        "query_units_per_second": 50,
        "burst_query_units": 50,
        "independent_of_tier": True,
    },
    "note": (
        "Web Pro/Max is not an API org. Local cap stays conservative until a key "
        "can report the account tier. Agent Tier 0 is 50 RPM / 1 QPS."
    ),
}


def api_key() -> str:
    return (os.environ.get("PERPLEXITY_API_KEY") or os.environ.get("PPLX_API_KEY") or "").strip()


def _headers() -> dict[str, str]:
    key = api_key()
    if not key:
        raise RuntimeError("PERPLEXITY_API_KEY is not set")
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _request(method: str, url: str, body: dict | None = None, timeout: float = 45) -> tuple[int, dict, dict]:
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=_headers(), method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            payload = json.loads(raw) if raw else {}
            headers = {k.lower(): v for k, v in resp.headers.items()}
            return resp.status, payload, headers
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {"error": raw[:400]}
        headers = {k.lower(): v for k, v in exc.headers.items()} if exc.headers else {}
        return exc.code, payload, headers


def _append_usage(row: dict) -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    with USAGE_LOG.open("a") as fh:
        fh.write(json.dumps(row) + "\n")


def cooldown_until() -> float:
    if not COOLDOWN_PATH.is_file():
        return 0.0
    try:
        return float(json.loads(COOLDOWN_PATH.read_text()).get("until", 0))
    except (json.JSONDecodeError, TypeError, ValueError):
        return 0.0


def set_cooldown(seconds: float) -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    COOLDOWN_PATH.write_text(json.dumps({"until": time.time() + seconds}))


def recent_rpm(window: int = 60) -> int:
    if not USAGE_LOG.is_file():
        return 0
    cutoff = time.time() - window
    n = 0
    for line in USAGE_LOG.read_text().splitlines()[-200:]:
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("ok") and row.get("ts", 0) >= cutoff:
            n += 1
    return n


def mcp_config() -> dict:
    configured = []
    if CURSOR_MCP.is_file():
        try:
            data = json.loads(CURSOR_MCP.read_text())
        except json.JSONDecodeError:
            data = {}
        servers = data.get("mcpServers") or data.get("servers") or {}
        for name, spec in servers.items():
            blob = json.dumps(spec).lower()
            if "perplexity" in name.lower() or "perplexity.ai" in blob:
                configured.append(
                    {
                        "name": name,
                        "url": spec.get("url") or spec.get("serverUrl"),
                        "command": spec.get("command"),
                    }
                )
    return {
        "cursor_mcp": str(CURSOR_MCP),
        "exists": CURSOR_MCP.is_file(),
        "perplexity_servers": configured,
        "official_remote": MCP_REMOTE,
        "official_docs": MCP_DOCS,
        "in_this_session": False,
        "note": "Official API MCP is https://api.perplexity.ai/mcp (OAuth or PERPLEXITY_API_KEY). It is not in this Cursor-bridge tool list until you Connect it in Settings → MCP.",
    }


def install_mcp() -> dict:
    CURSOR_MCP.parent.mkdir(parents=True, exist_ok=True)
    data = {}
    if CURSOR_MCP.is_file():
        try:
            data = json.loads(CURSOR_MCP.read_text())
        except json.JSONDecodeError:
            data = {}
    servers = data.setdefault("mcpServers", {})
    added = []
    if "perplexity" not in servers:
        servers["perplexity"] = {"url": MCP_REMOTE}
        added.append("perplexity")
    if "perplexity-docs" not in servers:
        servers["perplexity-docs"] = {"url": MCP_DOCS}
        added.append("perplexity-docs")
    CURSOR_MCP.write_text(json.dumps(data, indent=2) + "\n")
    return {
        "wrote": str(CURSOR_MCP),
        "added": added,
        "next": "Cursor Settings → Tools & MCP → Connect next to perplexity (OAuth, no key in the file).",
    }


def usage_status() -> dict:
    key = bool(api_key())
    cool = cooldown_until()
    rpm = recent_rpm()
    probe = None
    if key and time.time() >= cool:
        status, payload, headers = _request("GET", MODELS_URL, timeout=15)
        probe = {
            "http": status,
            "retry_after": headers.get("retry-after"),
            "error": (payload.get("error") if isinstance(payload, dict) else None),
        }
        if status == 429:
            try:
                wait = float(headers.get("retry-after") or 60)
            except ValueError:
                wait = 60
            set_cooldown(wait)
            cool = cooldown_until()
        elif status in {401, 403}:
            probe["hint"] = "API key rejected. Web Pro/Max login is not an API key."
    return {
        "api_key": "set" if key else "missing",
        "recent_rpm": rpm,
        "local_rpm_cap": DEFAULT_RPM,
        "cooldown_remaining_s": max(0, int(cool - time.time())),
        "probe": probe,
        "mcp": mcp_config(),
        "official_limits": OFFICIAL_LIMITS,
        "docs": {
            "agent": "POST /v1/agent (presets fast/low/medium/high/xhigh; Tier 0 = 50 RPM / 1 QPS)",
            "sonar": "POST /v1/sonar until 2026-09-27",
            "search": "POST /search (50 query units/s, independent of usage tier)",
            "tiers": "https://docs.perplexity.ai/docs/admin/rate-limits-usage-tiers",
            "mcp": MCP_REMOTE,
        },
        "web_plan": "Signed-in Chrome is the consumer Pro/Max session. API credits are a separate API organization.",
    }


def api_available() -> tuple[bool, str]:
    if not api_key():
        return False, "no PERPLEXITY_API_KEY"
    if time.time() < cooldown_until():
        return False, f"api cooldown {int(cooldown_until() - time.time())}s"
    if recent_rpm() >= DEFAULT_RPM:
        return False, f"local rpm cap {DEFAULT_RPM}"
    return True, "ok"


def ask(query: str, preset: str = "low") -> dict:
    if preset not in PRESETS:
        preset = "low"
    t0 = time.time()
    status, payload, headers = _request(
        "POST",
        AGENT_URL,
        {"preset": preset, "input": query},
        timeout=90,
    )
    row = {
        "ts": time.time(),
        "ok": status == 200,
        "http": status,
        "via": "agent",
        "preset": preset,
        "elapsed_s": round(time.time() - t0, 2),
    }
    if status == 429:
        try:
            set_cooldown(float(headers.get("retry-after") or 60))
        except ValueError:
            set_cooldown(60)
        _append_usage(row)
        raise RuntimeError("API 429 rate limit; falling back is the caller's job")
    if status != 200:
        # Sonar still lives until 2026-09-27.
        status2, payload2, headers2 = _request(
            "POST",
            SONAR_URL,
            {"model": "sonar", "messages": [{"role": "user", "content": query}]},
            timeout=90,
        )
        row["via"] = "sonar"
        row["http"] = status2
        row["ok"] = status2 == 200
        _append_usage(row)
        if status2 == 429:
            try:
                set_cooldown(float(headers2.get("retry-after") or 60))
            except ValueError:
                set_cooldown(60)
            raise RuntimeError("API 429 rate limit")
        if status2 != 200:
            raise RuntimeError(f"API {status}/{status2}: {payload or payload2}")
        text = ""
        choices = payload2.get("choices") or []
        if choices:
            text = ((choices[0].get("message") or {}).get("content")) or ""
        return {
            "via": "api/sonar",
            "text": text,
            "raw_usage": payload2.get("usage"),
            "id": payload2.get("id"),
        }
    _append_usage(row)
    text = payload.get("output_text") or ""
    if not text:
        for item in payload.get("output") or []:
            if isinstance(item, dict) and item.get("type") in {"message", "output_text"}:
                content = item.get("content")
                if isinstance(content, str):
                    text += content
                elif isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict) and part.get("text"):
                            text += part["text"]
    return {
        "via": f"api/agent:{preset}",
        "text": text,
        "id": payload.get("id"),
        "model": payload.get("model"),
        "raw_usage": payload.get("usage"),
    }


def search_web(query: str) -> dict:
    status, payload, headers = _request("POST", SEARCH_URL, {"query": query}, timeout=30)
    _append_usage({"ts": time.time(), "ok": status == 200, "http": status, "via": "search"})
    if status == 429:
        try:
            set_cooldown(float(headers.get("retry-after") or 30))
        except ValueError:
            set_cooldown(30)
        raise RuntimeError("Search API 429")
    if status != 200:
        raise RuntimeError(f"Search API {status}: {payload}")
    return {"via": "api/search", "result": payload}
