"""Pick official API vs signed-in Chrome for a pi-p action."""

from __future__ import annotations

from urllib.parse import quote

from api import api_available, api_key, mcp_config

BROWSER_ONLY = {
    "tabs",
    "focus",
    "read",
    "md",
    "download",
    "steer",
    "open",
    "new",
    "library",
    "workspace",
    "chrome-prep",
}
API_ELIGIBLE = {"search", "ask", "query"}


def search_url(query: str) -> str:
    return "https://www.perplexity.ai/search?q=" + quote(query)


def _mcp_fields() -> dict:
    mcp = mcp_config()
    return {
        "mcp_configured": bool(mcp.get("perplexity_servers")),
        "mcp_in_session": bool(mcp.get("in_this_session")),
    }


def decide(action: str, via: str = "auto") -> dict:
    action = action.strip().lower()
    via = (via or "auto").strip().lower()
    extra = _mcp_fields()
    if action in BROWSER_ONLY:
        return {
            "action": action,
            "via": "browser",
            "reason": "library/workspace/live pane are not in the official API",
            **extra,
        }
    if action not in API_ELIGIBLE:
        return {"action": action, "via": "unknown", "reason": "unknown action", **extra}
    if via == "browser":
        return {"action": action, "via": "browser", "reason": "forced --via browser", **extra}
    if via == "mcp":
        configured = extra["mcp_configured"]
        return {
            "action": action,
            "via": "mcp" if configured else "api",
            "reason": (
                "MCP configured in ~/.cursor/mcp.json (Connect in Cursor Settings to use in-session)"
                if configured
                else "MCP not connected; use official API if keyed"
            ),
            **extra,
        }
    if via == "api":
        ok, why = api_available()
        return {
            "action": action,
            "via": "api" if ok else "browser",
            "reason": why if ok else f"api unavailable ({why}); browser fallback",
            **extra,
        }
    # auto
    if not api_key():
        return {
            "action": action,
            "via": "browser",
            "reason": "no PERPLEXITY_API_KEY; use signed-in Chrome (web plan)",
            **extra,
        }
    ok, why = api_available()
    if not ok:
        return {"action": action, "via": "browser", "reason": why, **extra}
    return {
        "action": action,
        "via": "api",
        "reason": "API key present and under local RPM/cooldown",
        **extra,
    }


def split(via: str = "auto") -> dict:
    """API vs Chrome split for every known action. No network, no new tabs."""
    browser = {action: decide(action, via) for action in sorted(BROWSER_ONLY)}
    api = {action: decide(action, via) for action in sorted(API_ELIGIBLE)}
    keyed = bool(api_key())
    return {
        "api_key": "set" if keyed else "missing",
        "search_via": api["search"]["via"],
        "search_reason": api["search"]["reason"],
        "browser_only": browser,
        "api_eligible": api,
        **_mcp_fields(),
        "web_plan": "Signed-in Chrome is the consumer Pro/Max session. API credits are a separate API organization.",
    }
