"""Apply aos.policy.v1 filters and transforms on catalogs, streams, and graph hops."""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field
from typing import Any, Iterable

SILENT = "silent"
TEXT_SURFACES = frozenset(
    {
        "stream.inbound",
        "stream.outbound",
        "stream.tts",
        "context",
        "memory",
        "cot",
        "moa",
        "graph.edge",
        "graph.node.introspect",
    }
)
CATALOG_SURFACES = frozenset(
    {
        "catalog.tools",
        "catalog.skills",
        "catalog.extensions",
        "catalog.prompts",
        "catalog.harness",
    }
)


def context_from_env(env: dict[str, str] | None = None, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    env = env or dict(os.environ)
    wrapper = (
        env.get("AOS_WRAPPER")
        or env.get("HERMES_WRAPPER")
        or ("herm-tui" if env.get("HERMES_TUI") else "")
        or env.get("PI_WRAPPER")
        or ""
    ).strip()
    provider = (env.get("AOS_PROVIDER") or env.get("HERMES_PROVIDER") or env.get("PI_PROVIDER") or "").strip()
    class_name = (env.get("AOS_POLICY_CLASS") or env.get("PI_PROFILE_CLASS") or "").strip()
    agent = (
        env.get("AOS_POLICY_AGENT")
        or env.get("PI_PROFILE_AGENT")
        or env.get("PI_AGENT")
        or env.get("HERMES_AGENT")
        or ""
    ).strip()
    bridge = [
        part.strip()
        for part in (env.get("AOS_BRIDGE_TOOLS") or env.get("PI_BRIDGE_TOOLS") or "").split(",")
        if part.strip()
    ]
    ctx = {
        "wrapper": wrapper,
        "provider": provider,
        "class": class_name,
        "agent": agent,
        "host_class": (env.get("AOS_HOST_CLASS") or env.get("HARNESS_HOST_CLASS") or "").strip(),
        "bridge_tools": bridge,
    }
    if extra:
        ctx.update(extra)
    return ctx


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _lower_set(values: Iterable[Any]) -> set[str]:
    return {str(item).strip().lower() for item in values if str(item).strip()}


def _match_any(value: str, candidates: Iterable[Any]) -> bool:
    needle = value.strip().lower()
    return needle in _lower_set(candidates)


def _when_clause(clause: Any, ctx: dict[str, Any]) -> bool:
    if not clause:
        return True
    if not isinstance(clause, dict):
        return True
    if "all" in clause:
        return all(_when_clause(item, ctx) for item in _as_list(clause["all"]))
    if "any" in clause:
        return any(_when_clause(item, ctx) for item in _as_list(clause["any"]))
    if "class_not" in clause:
        current = str(ctx.get("class") or "").strip().lower()
        return current not in _lower_set(_as_list(clause["class_not"]))
    checks = [
        ("wrapper", "wrapper"),
        ("provider", "provider"),
        ("class", "class"),
        ("agent", "agent"),
        ("host_class", "host_class"),
    ]
    for key, ctx_key in checks:
        if key not in clause:
            continue
        if not _match_any(str(ctx.get(ctx_key) or ""), _as_list(clause[key])):
            return False
    if "bridge_tools" in clause:
        have = _lower_set(_as_list(ctx.get("bridge_tools")))
        want = _lower_set(_as_list(clause["bridge_tools"]))
        if not (have & want):
            return False
    return True


def policy_applies(policy: dict[str, Any], ctx: dict[str, Any]) -> bool:
    if not policy.get("enabled", True):
        return False
    return _when_clause(policy.get("when") or {}, ctx)


def applicable_policies(bundle: dict[str, Any], ctx: dict[str, Any]) -> list[dict[str, Any]]:
    policies = [p for p in bundle.get("policies") or [] if policy_applies(p, ctx)]
    return sorted(policies, key=lambda item: (-int(item.get("priority") or 0), item.get("id") or ""))


def _rule_surfaces(rule: dict[str, Any]) -> list[str]:
    return [str(item) for item in _as_list(rule.get("surface"))]


def rules_for(policy: dict[str, Any], surface: str) -> list[dict[str, Any]]:
    return [rule for rule in policy.get("rules") or [] if surface in _rule_surfaces(rule)]


def normalize_utterance(text: str) -> str:
    """Case-fold, strip quotes/trailing punct, collapse space. Exact-sentence key."""
    out = (text or "").strip().lower()
    out = out.replace("\u2019", "'").replace("\u2018", "'")
    out = re.sub(r"[\"“”]", "", out)
    out = re.sub(r"[.!?…,;:]+$", "", out)
    out = re.sub(r"\s+", " ", out)
    return out.strip()


def split_sentences(text: str) -> list[str]:
    if not (text or "").strip():
        return []
    parts = re.findall(r".+?(?:[.!?]+(?:\s+|$)|$)", text, flags=re.S)
    return [part for part in parts if part.strip()] or [text]


def _pick_replace(rule: dict[str, Any], seed: str) -> str:
    phrases = [str(item).strip() for item in _as_list(rule.get("replace")) if str(item).strip()]
    if not phrases:
        return ""
    turn = os.environ.get("AOS_VOICE_TURN", "")
    digest = hashlib.sha256(f"{seed}\n{turn}".encode("utf-8")).hexdigest()
    return phrases[int(digest, 16) % len(phrases)]


def _rewrite_sentences(text: str, needles_norm: set[str], replacement: str) -> str:
    if not replacement:
        return text
    out: list[str] = []
    changed = False
    for part in split_sentences(text):
        if normalize_utterance(part) in needles_norm:
            gap = re.match(r".*?(\s*)$", part, flags=re.S)
            suffix = gap.group(1) if gap else ""
            repl = replacement.rstrip()
            if repl and repl[-1] not in ".!?":
                repl += "."
            out.append(repl + suffix)
            changed = True
        else:
            out.append(part)
    return "".join(out) if changed else text


def _name_matches(name: str, match: dict[str, Any]) -> bool:
    if not match:
        return True
    kind = str(match.get("kind") or "name").lower()
    needles = [str(item) for item in _as_list(match.get("any") or match.get("value"))]
    text = name
    lowered = text.lower()
    if kind == "all":
        return True
    if kind == "name":
        return lowered in {item.lower() for item in needles}
    if kind == "prefix":
        return any(lowered.startswith(item.lower()) for item in needles)
    if kind == "contains":
        return any(item.lower() in lowered for item in needles)
    if kind == "regex":
        return any(re.search(item, text, re.I) for item in needles)
    if kind == "text":
        return any(item.lower() in lowered for item in needles)
    if kind == "exact":
        key = normalize_utterance(text)
        return key in {normalize_utterance(item) for item in needles}
    if kind == "sentence":
        keys = {normalize_utterance(item) for item in needles}
        return any(normalize_utterance(part) in keys for part in split_sentences(text))
    return False


def _apply_rewrite(text: str, rule: dict[str, Any]) -> str:
    match = rule.get("match") or {}
    kind = str(match.get("kind") or "text").lower()
    patterns = [str(item) for item in _as_list(match.get("any"))]
    if not _name_matches(text, match):
        return text
    replacement = _pick_replace(rule, text)
    if kind == "exact":
        return replacement or text
    if kind == "sentence":
        keys = {normalize_utterance(item) for item in patterns}
        return _rewrite_sentences(text, keys, replacement)
    if not patterns:
        return replacement or text
    if not replacement:
        return _strip_patterns(text, patterns)
    out = text
    for pattern in patterns:
        out = re.sub(re.escape(pattern), replacement, out, flags=re.I)
    return out


def _item_name(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("name") or item.get("id") or item.get("tool") or "")
    return str(item)


def filter_catalog(
    bundle: dict[str, Any],
    surface: str,
    items: list[Any],
    ctx: dict[str, Any],
) -> list[Any]:
    if surface not in CATALOG_SURFACES:
        raise ValueError(f"not a catalog surface: {surface}")
    names = [_item_name(item) for item in items]
    kept = list(items)
    exclusive = False
    allow_names: set[str] = set()
    deny_names: set[str] = set()
    remaps: list[tuple[str, str]] = []
    for policy in applicable_policies(bundle, ctx):
        if surface not in (policy.get("surfaces") or []) and not rules_for(policy, surface):
            continue
        if str(policy.get("mode") or "filter") == "exclusive":
            exclusive = True
        for rule in rules_for(policy, surface):
            action = rule.get("action")
            matched = [name for name in names if _name_matches(name, rule.get("match") or {})]
            if action == "allow":
                allow_names.update(matched if matched else [name for name in names if _name_matches(name, rule.get("match") or {})])
                if not names:
                    continue
            elif action == "deny" or action == "drop":
                if (rule.get("match") or {}).get("kind") == "all":
                    deny_names.update(names)
                else:
                    deny_names.update(matched)
            elif action == "remap" and rule.get("remap_to"):
                for name in matched:
                    remaps.append((name, str(rule["remap_to"])))
    if exclusive:
        kept = [item for item in kept if _item_name(item) in allow_names and _item_name(item) not in deny_names]
    else:
        kept = [item for item in kept if _item_name(item) not in deny_names]
    if remaps:
        mapping = {src: dst for src, dst in remaps}
        rewritten = []
        for item in kept:
            name = _item_name(item)
            if name not in mapping:
                rewritten.append(item)
                continue
            if isinstance(item, dict):
                copy = dict(item)
                copy["name"] = mapping[name]
                rewritten.append(copy)
            else:
                rewritten.append(mapping[name])
        kept = rewritten
    return kept


def _strip_patterns(text: str, patterns: list[str]) -> str:
    out = text
    for pattern in patterns:
        if not pattern:
            continue
        out = re.sub(re.escape(pattern), "", out, flags=re.I)
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out


def collect_text_patterns(bundle: dict[str, Any], surface: str, ctx: dict[str, Any], *, silent_only: bool = False) -> list[str]:
    patterns: list[str] = []
    for policy in applicable_policies(bundle, ctx):
        for rule in rules_for(policy, surface):
            if rule.get("action") not in {"strip", "redact", "rewrite"}:
                continue
            if silent_only and str(rule.get("visibility") or "visible") != SILENT:
                continue
            patterns.extend(str(item) for item in _as_list((rule.get("match") or {}).get("any")))
    return patterns


def transform_text(
    bundle: dict[str, Any],
    surface: str,
    text: str,
    ctx: dict[str, Any],
) -> str:
    if surface not in TEXT_SURFACES and surface not in {"context", "memory"}:
        raise ValueError(f"not a text surface: {surface}")
    out = text
    for policy in applicable_policies(bundle, ctx):
        for rule in rules_for(policy, surface):
            action = rule.get("action")
            if action not in {"strip", "redact", "rewrite", "drop"}:
                continue
            match = rule.get("match") or {}
            patterns = [str(item) for item in _as_list(match.get("any"))]
            if action == "drop" and _name_matches(out, match):
                return ""
            if action in {"strip", "redact"}:
                out = _strip_patterns(out, patterns)
                if action == "redact" and rule.get("replace"):
                    # already stripped; optional replacement only if requested and visible
                    if str(rule.get("visibility") or "visible") != SILENT:
                        out = out + str(_pick_replace(rule, text) or rule.get("replace") or "")
            if action == "rewrite":
                out = _apply_rewrite(out, rule)
    return out


DEFAULT_CONTINUATION = (
    "Still with the last confirmed fleet snapshot. Next I'll check the live panes."
)


def apply_tts(
    bundle: dict[str, Any],
    text: str,
    ctx: dict[str, Any],
    *,
    fallback: str | None = None,
) -> str:
    """Filter a TTS transcript. Empty after rewrite becomes a continuation, never an error."""
    out = transform_text(bundle, "stream.tts", text or "", ctx)
    spoken = (out or "").strip()
    if spoken:
        return spoken
    return (fallback or DEFAULT_CONTINUATION).strip()


@dataclass
class StreamState:
    hold: str = ""
    window: int = 0


@dataclass
class StreamResult:
    emit: str
    hold: str
    dropped: bool = False
    annotations: list[str] = field(default_factory=list)


def _max_pattern_len(patterns: list[str]) -> int:
    return max((len(p) for p in patterns), default=0)


def apply_stream(
    bundle: dict[str, Any],
    surface: str,
    chunk: str,
    ctx: dict[str, Any],
    state: StreamState | None = None,
    *,
    final: bool = False,
) -> StreamResult:
    state = state or StreamState()
    patterns = collect_text_patterns(bundle, surface, ctx)
    sentence_hold = False
    for policy in applicable_policies(bundle, ctx):
        for rule in rules_for(policy, surface):
            if rule.get("action") not in {"strip", "redact", "rewrite", "drop"}:
                continue
            kind = str((rule.get("match") or {}).get("kind") or "").lower()
            if kind in {"sentence", "exact"}:
                sentence_hold = True
                break
        if sentence_hold:
            break
    if not patterns and not sentence_hold:
        emit = state.hold + chunk
        state.hold = ""
        return StreamResult(emit=emit, hold="")
    window = max(_max_pattern_len(patterns), state.window)
    state.window = window
    buf = state.hold + chunk
    transformed = transform_text(bundle, surface, buf, ctx)
    if final:
        state.hold = ""
        return StreamResult(emit=transformed, hold="")
    if sentence_hold:
        last = max((transformed.rfind(mark) for mark in ".!?"), default=-1)
        if last < 0:
            state.hold = transformed
            return StreamResult(emit="", hold=transformed)
        emit, hold = transformed[: last + 1], transformed[last + 1 :]
        state.hold = hold
        return StreamResult(emit=emit, hold=hold)
    if len(transformed) <= window:
        state.hold = transformed
        return StreamResult(emit="", hold=transformed)
    emit, hold = transformed[:-window], transformed[-window:]
    state.hold = hold
    return StreamResult(emit=emit, hold=hold)


def apply_edge(
    bundle: dict[str, Any],
    payload: str,
    ctx: dict[str, Any],
    *,
    src: str = "",
    dst: str = "",
) -> str:
    edge_ctx = dict(ctx)
    if src:
        edge_ctx["edge_src"] = src
    if dst:
        edge_ctx["edge_dst"] = dst
    return transform_text(bundle, "graph.edge", payload, edge_ctx)


def apply_introspect(
    bundle: dict[str, Any],
    view: str,
    ctx: dict[str, Any],
    *,
    node: str = "",
) -> str:
    node_ctx = dict(ctx)
    if node:
        node_ctx["node"] = node
    return transform_text(bundle, "graph.node.introspect", view, node_ctx)


def public_status(bundle: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    """Operator-safe summary. Silent rule bodies stay out of model tokens."""
    applied = applicable_policies(bundle, ctx)
    silent = 0
    for policy in applied:
        for rule in policy.get("rules") or []:
            if str(rule.get("visibility") or "visible") == SILENT:
                silent += 1
                break
    return {
        "schema": "aos.policy.status.v1",
        "active": len(applied),
        "silent": silent,
        "ids": [p["id"] for p in applied],
    }
