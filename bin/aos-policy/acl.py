"""Identity + ACL/JIT grants for aos.policy documents."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from schema import ACL_SCHEMA, default_home, load_yaml_file, normalize_acl

ISO = "%Y-%m-%dT%H:%M:%SZ"


def now() -> datetime:
    return datetime.now(timezone.utc)


def parse_ttl(ttl: str) -> datetime | None:
    text = (ttl or "").strip().lower()
    if not text or text in {"none", "0", "permanent"}:
        return None
    unit = text[-1]
    try:
        amount = int(text[:-1] if unit.isalpha() else text)
    except ValueError as exc:
        raise ValueError(f"bad ttl: {ttl}") from exc
    if unit == "s":
        delta = timedelta(seconds=amount)
    elif unit == "m":
        delta = timedelta(minutes=amount)
    elif unit == "h":
        delta = timedelta(hours=amount)
    elif unit == "d":
        delta = timedelta(days=amount)
    elif text[-1].isdigit():
        delta = timedelta(seconds=int(text))
    else:
        raise ValueError(f"bad ttl: {ttl}")
    return now() + delta


def _expired(expires: Any) -> bool:
    if not expires:
        return False
    try:
        when = datetime.fromisoformat(str(expires).replace("Z", "+00:00"))
    except ValueError:
        return False
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when <= now()


def _principal_hit(principal: dict[str, Any], actor: dict[str, Any]) -> bool:
    agents = [str(item).lower() for item in principal.get("agent") or [] if str(item).strip()]
    classes = [str(item).lower() for item in principal.get("class") or [] if str(item).strip()]
    agent = str(actor.get("agent") or "").strip().lower()
    class_name = str(actor.get("class") or "").strip().lower()
    if agents and agent not in agents:
        return False
    if classes and class_name not in classes:
        return False
    return bool(agents or classes)


def _policy_hit(patterns: list[str], policy_id: str) -> bool:
    if not patterns or "*" in patterns:
        return True
    return policy_id in patterns or any(policy_id.startswith(p.rstrip("*")) for p in patterns if p.endswith("*"))


def actor_from_ctx(ctx: dict[str, Any]) -> dict[str, str]:
    return {
        "agent": str(ctx.get("agent") or "").strip(),
        "class": str(ctx.get("class") or "").strip(),
    }


def allowed(
    bundle: dict[str, Any],
    actor: dict[str, Any],
    capability: str,
    policy_id: str = "*",
) -> bool:
    grants = (bundle.get("acl") or {}).get("grants") or []
    for grant in grants:
        if _expired(grant.get("expires")):
            continue
        if not _principal_hit(grant.get("principal") or {}, actor):
            continue
        if capability not in (grant.get("capabilities") or []):
            continue
        if not _policy_hit(list(grant.get("policies") or ["*"]), policy_id):
            continue
        return True
    return False


def require(
    bundle: dict[str, Any],
    actor: dict[str, Any],
    capability: str,
    policy_id: str = "*",
) -> None:
    if not allowed(bundle, actor, capability, policy_id):
        who = actor.get("agent") or actor.get("class") or "unknown"
        raise PermissionError(f"aos-policy: {who} lacks {capability} on {policy_id}")


def overlay_acl_path(home: Path | None = None) -> Path:
    return Path(home or default_home()) / "acl" / "grants.yaml"


def add_jit_grant(
    *,
    actor: dict[str, Any],
    bundle: dict[str, Any],
    agent: str,
    capability: str,
    policies: list[str],
    ttl: str,
    class_name: str = "",
    home: Path | None = None,
) -> dict[str, Any]:
    require(bundle, actor, "policy.grant", policies[0] if len(policies) == 1 else "*")
    expires = parse_ttl(ttl)
    grant = {
        "id": f"jit-{agent}-{capability}-{int(now().timestamp())}",
        "principal": {"agent": [agent], "class": [class_name] if class_name else []},
        "capabilities": [capability],
        "policies": policies or ["*"],
        "expires": expires.strftime(ISO) if expires else None,
        "source": "jit",
    }
    path = overlay_acl_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = normalize_acl(load_yaml_file(path), source=str(path)) if path.exists() else {
        "schema": ACL_SCHEMA,
        "grants": [],
    }
    existing["grants"].append(grant)
    lines = ["schema: aos.acl.v1", "grants:"]
    for item in existing["grants"]:
        lines.append(f"  - id: {item['id']}")
        lines.append("    principal:")
        agents = item.get("principal", {}).get("agent") or []
        classes = item.get("principal", {}).get("class") or []
        if agents:
            lines.append("      agent:")
            for name in agents:
                lines.append(f"        - {name}")
        if classes:
            lines.append("      class:")
            for name in classes:
                lines.append(f"        - {name}")
        lines.append("    capabilities:")
        for cap in item.get("capabilities") or []:
            lines.append(f"      - {cap}")
        lines.append("    policies:")
        for policy in item.get("policies") or ["*"]:
            lines.append(f"      - {policy}")
        if item.get("expires"):
            lines.append(f"    expires: {item['expires']}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    path.chmod(0o600)
    return grant
