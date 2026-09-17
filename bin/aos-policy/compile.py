"""Compile aos.policy.v1 into harness-native permission sidecars."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from engine import applicable_policies, collect_text_patterns, filter_catalog
from schema import default_home

ADAPTERS = ("cursor", "claude", "codex", "pi", "hermes", "herm-tui", "graph-edge")

CURSOR_NATIVE = [
    "Task",
    "Shell",
    "Grep",
    "Delete",
    "WebSearch",
    "WebFetch",
    "ReadLints",
    "EditNotebook",
    "TodoWrite",
    "StrReplace",
    "Write",
    "Read",
    "Glob",
    "AwaitShell",
    "GetDynamicTools",
    "FetchMcpResource",
    "SwitchMode",
    "CallDynamicTool",
    "GenerateImage",
    "CreateGoal",
    "UpdateGoal",
    "Edit",
    "Bash",
    "NotebookEdit",
    "Browser",
]


def _catalog_decision(bundle: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    sample = list(CURSOR_NATIVE) + [
        "pi__subagent",
        "pi__atop_plan",
        "hermes_run",
        "profile_manifest",
        "aos_policy",
        "aos_voice_brief",
        "aos_voice_filter",
        "query_granola_meetings",
        "list_meetings",
    ]
    kept = {str(item) for item in filter_catalog(bundle, "catalog.tools", sample, ctx)}
    named = {"profile_manifest", "aos_policy", "aos_voice_brief", "aos_voice_filter"}
    allow = sorted(name for name in kept if name.startswith(("pi__", "hermes_", "herm_")) or name in named)
    deny = sorted(name for name in sample if name not in kept)
    exclusive = any(str(p.get("mode")) == "exclusive" for p in applicable_policies(bundle, ctx))
    silent_patterns = collect_text_patterns(bundle, "stream.outbound", ctx, silent_only=True)
    silent_patterns += collect_text_patterns(bundle, "stream.tts", ctx, silent_only=True)
    silent_patterns += collect_text_patterns(bundle, "cot", ctx, silent_only=True)
    silent_patterns += collect_text_patterns(bundle, "moa", ctx, silent_only=True)
    return {
        "allow": allow,
        "deny": deny,
        "exclusive": exclusive,
        "silent_patterns": sorted(set(silent_patterns)),
        "active": [p["id"] for p in applicable_policies(bundle, ctx)],
    }


def compile_adapter(bundle: dict[str, Any], adapter: str, ctx: dict[str, Any]) -> dict[str, Any]:
    if adapter not in ADAPTERS:
        raise ValueError(f"unknown adapter: {adapter}")
    decision = _catalog_decision(bundle, ctx)
    if adapter == "cursor":
        return {
            "schema": "aos.policy.cursor.v1",
            "approvalMode": "allowlist",
            "permissions": {"allow": decision["allow"], "deny": decision["deny"]},
            "silent": True,
            "policies": decision["active"],
        }
    if adapter == "claude":
        return {
            "schema": "aos.policy.claude.v1",
            "permissions": {"allow": decision["allow"], "deny": decision["deny"]},
            "silent": True,
            "policies": decision["active"],
        }
    if adapter == "codex":
        return {
            "schema": "aos.policy.codex.v1",
            "approval_policy": "on-request",
            "aos_policy": {
                "allowed_tools": decision["allow"],
                "denied_tools": decision["deny"],
                "silent": True,
            },
            "policies": decision["active"],
        }
    if adapter in {"pi", "hermes", "herm-tui"}:
        return {
            "schema": f"aos.policy.{adapter}.v1",
            "exclusive": decision["exclusive"],
            "tools": {"allow": decision["allow"], "deny": decision["deny"]},
            "silentPatterns": decision["silent_patterns"],
            "policies": decision["active"],
        }
    return {
        "schema": "aos.policy.graph-edge.v1",
        "wrap": {"edges": True, "introspect": True, "engine": "aos.policy.v1"},
        "silentPatterns": decision["silent_patterns"],
        "policies": decision["active"],
    }


def _toml(payload: dict[str, Any]) -> str:
    lines = [
        "approval_policy = \"on-request\"",
        "",
        "[aos_policy]",
        f"silent = {str(payload['aos_policy']['silent']).lower()}",
    ]
    allow = payload["aos_policy"]["allowed_tools"]
    deny = payload["aos_policy"]["denied_tools"]
    if allow:
        lines.append("allowed_tools = [" + ", ".join(json.dumps(x) for x in allow) + "]")
    if deny:
        lines.append("denied_tools = [" + ", ".join(json.dumps(x) for x in deny) + "]")
    return "\n".join(lines) + "\n"


def write_compiled(
    bundle: dict[str, Any],
    ctx: dict[str, Any],
    *,
    dest: Path | None = None,
    adapters: list[str] | None = None,
) -> Path:
    dest = Path(dest or (default_home() / "compiled"))
    dest.mkdir(parents=True, exist_ok=True)
    chosen = adapters or list(ADAPTERS)
    index = {"schema": "aos.policy.compiled.v1", "adapters": {}}
    for adapter in chosen:
        payload = compile_adapter(bundle, adapter, ctx)
        if adapter == "codex":
            path = dest / "codex.toml"
            path.write_text(_toml(payload), encoding="utf-8")
        else:
            path = dest / f"{adapter}.json"
            path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        index["adapters"][adapter] = str(path)
    resolved = dest / "resolved.json"
    slim = {
        "schema": bundle.get("schema"),
        "name": bundle.get("name"),
        "policies": [
            {
                "id": p["id"],
                "priority": p["priority"],
                "enabled": p["enabled"],
                "mode": p["mode"],
                "when": p.get("when") or {},
                "surfaces": p.get("surfaces") or [],
                "rules": p.get("rules") or [],
            }
            for p in bundle.get("policies") or []
        ],
    }
    resolved.write_text(json.dumps(slim, indent=2) + "\n", encoding="utf-8")
    (dest / "index.json").write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    return dest


def silent_rule_count(bundle: dict[str, Any], ctx: dict[str, Any]) -> int:
    count = 0
    for policy in applicable_policies(bundle, ctx):
        for rule in policy.get("rules") or []:
            if str(rule.get("visibility") or "visible") == "silent":
                count += 1
    return count
