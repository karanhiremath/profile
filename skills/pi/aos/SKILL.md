---
name: aos
description: Agent OS install — Hermes/pi/Codex/Cursor skill and toolset wiring, harness-sync, isolated HERMES_HOME skills links.
---

# aos

Make skills and toolsets actually load in every harness.

## Discovery roots

| Harness | Root |
|---|---|
| pi | `~/.pi/agent/skills` (linked from `~/src/profile/skills/pi`) |
| Codex | `~/.codex/skills` |
| Cursor-in-pi | union of pi/agents/claude/cursor/codex — one name per root (`bin/atop/resolve-skill-conflicts`) |
| Hermes Cos/CosW | `$HERMES_HOME/skills` under `~/.local/share/hermes-agents/<profile>` |
| Default herm | `~/.hermes/skills` |

## Install

```
~/src/profile/bin/atop/harness-sync apply
# isolated homes also get links from hermes_agents.materialize _ensure_skill_links
```

Official Hermes autonomous-ai-agents (incl. grok/codex/claude-code) live in
`~/src/hermes-agent/skills/autonomous-ai-agents` and
`~/src/hermes-agent/optional-skills/autonomous-ai-agents`. Isolated homes do
**not** inherit `~/.hermes/skills` — they must be linked.

## Persist

TUI Config writes `config.yaml`. `agents up` rematerializes from profile YAML
unless `HERMES_AGENT_FORCE_CONFIG=1`. Theme pins use `nighttideDefault`.

Live Cos/pi prompt coordination: `aos buf` / `atop vi <id>` (skill `atop-vi`). Never send-keys. Buffer catalog/get/apply is `aos-buf` (`just aos-buf`). Many Cos panes per home; each is its own Hermes session. Do not share a rendered TUI.

## Filter + policy engine

First-class AOS primitive. Same documents filter/transform inbound bytes,
context, memory, catalogs (tools/skills/extensions/prompts/harness),
CoT/MoA, and graph-eng edges / node introspection.

```
just aos-policy
aos policy apply --wrapper herm-tui --provider cursor
aos policy eval --surface catalog.tools --wrapper herm-tui --provider cursor
```

| Path | Role |
|---|---|
| `config/aos/policy` | bundled schema, policies, adapters, ACL |
| `bin/aos-policy` | source-of-truth engine + compile |
| `config/pi/packages/aos-policy-engine` | in-process pi / herm-tui hooks |
| `~/.local/share/aos/policy` | overlay + compiled sidecars |

`put` / `grant` require agent identity + ACL/JIT (`cos` / `cosw` /
`aos-policy-editor`, or a JIT grant). Silent rules (herm-tui + Cursor
exclusive) must never appear in CoT, MoA, or human-visible tokens.
Adapters compile into Cursor / Claude / Codex / pi / Hermes permission
sidecars.
