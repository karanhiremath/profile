# Codex / Cursor Instructions — profile

Tool-only repo. No Cartesia project context, customer data, or work notes.

## Cursor Agent CLI

| Item | Path |
|------|------|
| Installer | `bin/cursor-cli/install` |
| Secure bootstrap | `bin/cursor-cli/setup` |
| User config | `~/.cursor/cli-config.json` |
| Project overrides | `<repo>/.cursor/cli.json` (merged at session start) |

### Bootstrap

```bash
just cursor-cli    # install/upgrade cursor-agent
just cursor-setup  # link agents/skills + validate models
```

### Model defaults (orchestrator samples)

| Role | Cursor model slug | Analog |
|------|-------------------|--------|
| Complex orchestration | `claude-opus-4-8-thinking-high` | Codex orchestrator / fleet designer |
| Implementation / validation | `gpt-5.5-high` | Codex gpt-5.5 workers |

Override per session: `cursor-agent --model <slug>`.

### Security defaults (enforced by setup + project cli.json)

- `approvalMode`: `allowlist` — never `--force` / `--yolo` for fleet work
- `sandbox.mode`: `disabled` on dev Macs; use cdev/cagent sandboxes for risky remote work
- Secrets: never commit; fleet secrets at `~/.local/share/fleet/` only
- No Cartesia proprietary paths in committed profile artifacts

### Hermes CoS/PM command layer

Profile owns only generic command wrappers; project/work details live in `~/src/karan.hiremath` or `~/src/hermes` registry/profile files.

- `cos` → `agents up chief-of-staff`
- `cosw` → `agents up chief-of-staff-work`
- `pm <project>` → attach/start the registered Hermes project-manager TUI tmux session
- `pl <project>` → attach the registered project-lead implementation-agent tmux session

For Hermes PM-managed Pi handoffs, the generic rule is mandatory: the handoff writer must emit a `pm_action_required` event on the project event bus telling the PM to register/spawn the replacement Pi agent with the handoff prompt. Do not hard-code Cartesia project state in profile; read project registries via `bin/hermes/project_sessions.py`.

### Fleet registry

`bin/nvim/lua/kh/agent_registry.lua` is the shared agent-type source for tmux/fleet UIs. Cursor is registered there when present.
