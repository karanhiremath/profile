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
