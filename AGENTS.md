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

### Inference backends, sandboxes, and the agent loop

| Tool | Declares | Install |
|------|----------|---------|
| `inf` | inference backends, local + hosted | `just inference` |
| `sbx` | project sandboxes and JIT leases | `just sandbox` |
| `loop` | backlog dispatch to coding agents | run in place |

Backends are declared once in `config/inference/backends.toml` and RENDERED into
each harness — never hardcode a provider/model pair in a harness config again.

```bash
inf list                                  # * marks the registry default
inf doctor                                # what this machine can run
inf probe <id>                            # must pass before binding
inf bind pi <id> --only --probe
agents up cosw --backend <id>             # per-launch override
```

`inf probe` is the gate: health, /v1/models, blocking chat, SSE that terminates
with a finish_reason, and the streaming-plus-tools shape a coding agent actually
sends. It fails closed. Do not bind a backend that has not passed it.

Sandbox access is lease-gated (`sbx grant --reason ... --ttl ...`); secrets need
to be in both the sandbox's `allow_env` and the active lease. Governance runs
through the `sandbox-warden` profile, which cannot widen a ceiling on its own.

Full SOP: `docs/local-model-testing.md`. Schema: `config/inference/SCHEMA.md`.

Work-only backends and sandboxes belong in the work overlay under
`~/src/karan.hiremath/agentic/`, which is first on both search paths. `validate`
rejects internal hostnames and work-boundary sandboxes in this public repo.

### Hermes CoS/PM command layer

Profile owns only generic command wrappers; project/work details live in `~/src/karan.hiremath` or `~/src/hermes` registry/profile files.

- `cos` → `agents up chief-of-staff`
- `cosw` → `agents up chief-of-staff-work`
- `pm <project>` → attach/start the registered Hermes project-manager TUI tmux session
- `pl <project>` → attach the registered project-lead implementation-agent tmux session

For Hermes PM-managed Pi handoffs, the generic rule is mandatory: the handoff writer must emit a `pm_action_required` event on the project event bus telling the PM to register/spawn the replacement Pi agent with the handoff prompt. Do not hard-code Cartesia project state in profile; read project registries via `bin/hermes/project_sessions.py`.

### Fleet registry

`bin/nvim/lua/kh/agent_registry.lua` is the shared agent-type source for tmux/fleet UIs. Cursor is registered there when present.
