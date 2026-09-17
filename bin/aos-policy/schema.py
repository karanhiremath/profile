"""aos.policy.v1 load + constrained YAML (no PyYAML required)."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

SCHEMA = "aos.policy.v1"
BUNDLE_SCHEMA = "aos.policy.bundle.v1"
ACL_SCHEMA = "aos.acl.v1"
RESOLVED_SCHEMA = "aos.policy.resolved.v1"

SURFACES = frozenset(
    {
        "stream.inbound",
        "stream.outbound",
        "stream.tts",
        "context",
        "memory",
        "catalog.tools",
        "catalog.skills",
        "catalog.extensions",
        "catalog.prompts",
        "catalog.harness",
        "cot",
        "moa",
        "graph.edge",
        "graph.node.introspect",
    }
)
ACTIONS = frozenset(
    {"allow", "deny", "drop", "redact", "rewrite", "strip", "remap", "wrap"}
)
CAPABILITIES = frozenset(
    {"policy.read", "policy.write", "policy.apply", "policy.compile", "policy.grant"}
)


def default_bundle_root() -> Path:
    override = os.environ.get("AOS_POLICY_ROOT", "").strip()
    if override:
        return Path(override).expanduser()
    here = Path(__file__).resolve()
    return here.parents[2] / "config" / "aos" / "policy"


def default_home() -> Path:
    override = os.environ.get("AOS_POLICY_HOME", "").strip()
    if override:
        return Path(override).expanduser()
    xdg = os.environ.get("XDG_DATA_HOME", "").strip()
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base / "aos" / "policy"


def expand_policy_path(value: str) -> str:
    home = str(default_home())
    text = value.replace("${AOS_POLICY_HOME}", home)
    return os.path.expanduser(os.path.expandvars(text))


def load_yaml(text: str) -> Any:
    lines = text.replace("\t", "  ").splitlines()
    cleaned: list[tuple[int, str]] = []
    for raw in lines:
        stripped = raw.rstrip()
        if not stripped or stripped.lstrip().startswith("#"):
            continue
        indent = len(stripped) - len(stripped.lstrip(" "))
        cleaned.append((indent, stripped[indent:]))
    if not cleaned:
        return {}
    value, _ = _parse_block(cleaned, 0, cleaned[0][0])
    return value


def _parse_block(lines: list[tuple[int, str]], idx: int, indent: int) -> tuple[Any, int]:
    if idx >= len(lines):
        return {}, idx
    if lines[idx][1].startswith("- "):
        return _parse_list(lines, idx, indent)
    return _parse_map(lines, idx, indent)


def _parse_map(lines: list[tuple[int, str]], idx: int, indent: int) -> tuple[dict[str, Any], int]:
    out: dict[str, Any] = {}
    while idx < len(lines):
        cur_indent, content = lines[idx]
        if cur_indent < indent:
            break
        if cur_indent > indent:
            raise ValueError(f"bad indent at: {content}")
        if content.startswith("- "):
            break
        if ":" not in content:
            raise ValueError(f"expected key: {content}")
        key, rest = content.split(":", 1)
        key = key.strip()
        rest = rest.strip()
        idx += 1
        if rest in {">", "|", ">-", "|-"}:
            chunks: list[str] = []
            while idx < len(lines) and lines[idx][0] > indent:
                chunks.append(lines[idx][1])
                idx += 1
            out[key] = " ".join(chunks) if rest.startswith(">") else "\n".join(chunks)
            continue
        if rest:
            out[key] = _parse_scalar(rest)
            continue
        if idx >= len(lines) or lines[idx][0] <= indent:
            out[key] = {}
            continue
        child_indent = lines[idx][0]
        value, idx = _parse_block(lines, idx, child_indent)
        out[key] = value
    return out, idx


def _parse_list(lines: list[tuple[int, str]], idx: int, indent: int) -> tuple[list[Any], int]:
    out: list[Any] = []
    while idx < len(lines):
        cur_indent, content = lines[idx]
        if cur_indent < indent:
            break
        if cur_indent > indent:
            raise ValueError(f"bad list indent at: {content}")
        if not content.startswith("- "):
            break
        item = content[2:].strip()
        idx += 1
        if not item:
            if idx < len(lines) and lines[idx][0] > indent:
                value, idx = _parse_block(lines, idx, lines[idx][0])
                out.append(value)
            else:
                out.append({})
            continue
        if item.endswith(":") and (idx >= len(lines) or lines[idx][0] > indent):
            key = item[:-1].strip()
            value, idx = _parse_block(lines, idx, lines[idx][0])
            out.append({key: value})
            continue
        if ":" in item and not item.startswith(("'", '"')):
            key, rest = item.split(":", 1)
            mapping: dict[str, Any] = {key.strip(): _parse_scalar(rest.strip()) if rest.strip() else {}}
            while idx < len(lines) and lines[idx][0] > indent and not lines[idx][1].startswith("- "):
                nested, idx = _parse_map(lines, idx, lines[idx][0])
                mapping.update(nested)
            out.append(mapping)
            continue
        out.append(_parse_scalar(item))
    return out, idx


def _parse_scalar(text: str) -> Any:
    if text in {"", "~", "null", "Null", "NULL"}:
        return None
    if text in {"true", "True", "yes"}:
        return True
    if text in {"false", "False", "no"}:
        return False
    if (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
        return text[1:-1]
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    if re.fullmatch(r"-?\d+\.\d+", text):
        return float(text)
    if text.startswith(">") or text.startswith("|"):
        return text[1:].strip()
    return text


def load_yaml_file(path: Path) -> Any:
    return load_yaml(path.read_text(encoding="utf-8"))


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _as_str_list(value: Any) -> list[str]:
    return [str(item) for item in _as_list(value)]


def normalize_policy(raw: dict[str, Any], *, source: str = "") -> dict[str, Any]:
    schema = str(raw.get("schema") or SCHEMA)
    if schema != SCHEMA:
        raise ValueError(f"{source}: expected {SCHEMA}, got {schema}")
    policy_id = str(raw.get("id") or "").strip()
    if not policy_id:
        raise ValueError(f"{source}: missing id")
    surfaces = _as_str_list(raw.get("surfaces"))
    for surface in surfaces:
        if surface not in SURFACES:
            raise ValueError(f"{source}: unknown surface {surface}")
    rules = []
    for idx, rule in enumerate(_as_list(raw.get("rules"))):
        if not isinstance(rule, dict):
            raise ValueError(f"{source}: rule {idx} is not a map")
        action = str(rule.get("action") or "").strip()
        if action not in ACTIONS:
            raise ValueError(f"{source}: rule {idx} bad action {action}")
        rule_surfaces = _as_str_list(rule.get("surface") or surfaces)
        for surface in rule_surfaces:
            if surface not in SURFACES:
                raise ValueError(f"{source}: rule {idx} unknown surface {surface}")
        match = rule.get("match") or {}
        if match and not isinstance(match, dict):
            raise ValueError(f"{source}: rule {idx} match must be a map")
        rules.append(
            {
                "id": str(rule.get("id") or f"rule-{idx}"),
                "surface": rule_surfaces,
                "action": action,
                "visibility": str(rule.get("visibility") or "visible"),
                "match": dict(match) if match else {},
                "replace": rule.get("replace"),
                "remap_to": rule.get("remap_to"),
            }
        )
    return {
        "schema": SCHEMA,
        "id": policy_id,
        "priority": int(raw.get("priority") or 0),
        "enabled": bool(raw.get("enabled", True)),
        "mode": str(raw.get("mode") or "filter"),
        "description": str(raw.get("description") or "").strip(),
        "when": raw.get("when") or {},
        "surfaces": surfaces,
        "rules": rules,
        "source": source,
    }


def normalize_acl(raw: dict[str, Any], *, source: str = "") -> dict[str, Any]:
    schema = str(raw.get("schema") or ACL_SCHEMA)
    if schema != ACL_SCHEMA:
        raise ValueError(f"{source}: expected {ACL_SCHEMA}, got {schema}")
    grants = []
    for idx, grant in enumerate(_as_list(raw.get("grants"))):
        if not isinstance(grant, dict):
            raise ValueError(f"{source}: grant {idx} is not a map")
        caps = _as_str_list(grant.get("capabilities"))
        for cap in caps:
            if cap not in CAPABILITIES:
                raise ValueError(f"{source}: unknown capability {cap}")
        principal = grant.get("principal") or {}
        if not isinstance(principal, dict):
            raise ValueError(f"{source}: grant {idx} principal must be a map")
        grants.append(
            {
                "id": str(grant.get("id") or f"grant-{idx}"),
                "principal": {
                    "agent": _as_str_list(principal.get("agent")),
                    "class": _as_str_list(principal.get("class")),
                },
                "capabilities": caps,
                "policies": _as_str_list(grant.get("policies")) or ["*"],
                "expires": grant.get("expires"),
                "source": source,
            }
        )
    return {"schema": ACL_SCHEMA, "grants": grants, "source": source}


def _policy_files(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(p for p in root.glob("*.yaml") if p.is_file())


def load_bundle(root: Path | None = None, home: Path | None = None) -> dict[str, Any]:
    root = Path(root or default_bundle_root())
    home = Path(home or default_home())
    bundle_path = root / "bundle.yaml"
    raw = load_yaml_file(bundle_path) if bundle_path.exists() else {}
    if raw and str(raw.get("schema") or BUNDLE_SCHEMA) != BUNDLE_SCHEMA:
        raise ValueError(f"{bundle_path}: expected {BUNDLE_SCHEMA}")
    overlay_spec = expand_policy_path(str(raw.get("overlay") or str(home / "overlay")))
    overlay = Path(overlay_spec)
    policies: dict[str, dict[str, Any]] = {}
    for directory in [root / "policies", overlay]:
        for path in _policy_files(directory):
            policy = normalize_policy(load_yaml_file(path), source=str(path))
            policies[policy["id"]] = policy
    order = _as_str_list(raw.get("load_order"))
    ordered = []
    seen = set()
    for policy_id in order:
        if policy_id in policies:
            ordered.append(policies[policy_id])
            seen.add(policy_id)
    for policy in sorted(policies.values(), key=lambda item: (-item["priority"], item["id"])):
        if policy["id"] not in seen:
            ordered.append(policy)
    acl_rel = str(raw.get("acl") or "acl/grants.yaml")
    acl_path = root / acl_rel
    acl = normalize_acl(load_yaml_file(acl_path), source=str(acl_path)) if acl_path.exists() else {
        "schema": ACL_SCHEMA,
        "grants": [],
        "source": "",
    }
    overlay_acl = home / "acl" / "grants.yaml"
    if overlay_acl.exists():
        extra = normalize_acl(load_yaml_file(overlay_acl), source=str(overlay_acl))
        acl["grants"].extend(extra["grants"])
    return {
        "schema": RESOLVED_SCHEMA,
        "name": str(raw.get("name") or "aos-default"),
        "root": str(root),
        "home": str(home),
        "overlay": str(overlay),
        "policies": ordered,
        "acl": acl,
    }
