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

Live Cos/pi prompt coordination: `atop live` then `~/src/profile/bin/atop/vi <herm-id>` (skill `atop-vi`). Layer health is `atop.live.v1` (`a-top` / `aos` / `aop` / `infra-*` / harness homes). Never send-keys. Many Cos panes per home; each is its own Hermes session. Do not share a rendered TUI.

## Cos / CosW runtime (P0)

Default Cos/CosW is **host-native** (`terminal.backend: local`). Sandbox `/root` + `/root/.cosw-host` is **opt-in** via `cosw-s <sandbox> [<instance>]` (unique id if instance omitted) or attach `*-s`. `cosw --sandbox` is the impl flag `cosw-s` execs — not the operator door.

Persona/SOUL/manual must match the backend. A host pane that follows sandbox paths is a known failure mode. Do not "fix" it by launching Podman. `agents up` rewrites `SOUL.md` from profile YAML — keep that persona host-native.

The sandbox mechanism itself still needs improvement (opt-in compose, mounts, host observer, instance isolation). Until then, host-native is the Cos/CosW contract. Playbooks: `cosw-host-native-runtime.md`, `cosw-s-sandbox.md`, `aos-requirements-alignment.md`. Gather → align → review → validate at each AOS layer before shipping Cos-voice or toolkit changes.
