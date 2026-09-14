---
name: a-top
description: Atop coordinator loop — job-bus, pi__subagent, persist case, never send-keys. Use when running as the fleet TUI coordinator (atop / cos / cosw).
---

# a-top

Coordinator for the atop / Cos / CosW plane.

## Rules

- Delegate via `pi__subagent` (wait=false). Do not call Cursor-native Task while the pi bridge is exposed.
- Steer through job-bus / inbox only. Never `tmux send-keys` or `herdr pane send-text`.
- Persist state to a csec case or `agentic/drafts/` — chat is not durable.
- One worktree per mutating repo. Do not edit a dirty shared checkout if a worktree exists.
- Read tool output directly. No `&& echo` status.

## Loop

1. Inventory (job-bus list + live panes). ACK seen jobs.
2. Spawn context oracles first (`herm-tui-context`, `pi-coding-agent-context`, `hermes-agent-context`).
3. Implementors only after a confirmed root cause.
4. Write findings/hypotheses as you go.

## Prompt buffers — `atop vi`

```
atop live           # sessions + AOS layers (atop.live.v1)
atop live --json
atop vi             # NEW nvim + live dashboard + telescope
a-top vi            # same
atop vi list
atop vi live
atop vi <id> get
atop vi <id> set --file PACKET.md
atop vi tty         # PTY capture (agent eval; no Cos send-keys)
atop tty --probe    # QEMU/UTM/Lima/SSH:2222 + host TTY inventory
```

Bare `atop` is the rust fleet TUI (`atop-tui`) — sess view shows STATE/NOW; `o` is aos layers. `<CR>` in telescope edits that harness prompt. `<leader>fv` refreshes. Never send-keys.

## Related

- `aos` — isolated-home skill sync + persist
- `aop` — index → `attach` / `handoff` / `session-compaction`
- `atop-vi` — CLI details
- `infra-herm` — overlay pin + Cursor registry. Do not kill live Cos panes.
