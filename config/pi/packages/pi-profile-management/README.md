# pi-profile-management

Data-driven agent class + tool/MCP scoping for pi.

Granola MCP and granola plugin skills load **only** for `librarian` and `notetaker` classes, and only when that profile is the active session (`PI_PROFILE_AGENT` / `PI_PROFILE_CLASS` / `/profile-class`).

Implementor, reviewer, planner, orchestrator, and context profiles deny Granola so meeting tools do not pollute those sessions.

## Manifest

`manifests/profiles.json` (`pi.profile-manifest.v1`)

- `classes` — granola policy, mcpDeny, skillsDeny/Allow
- `agents` — agent name → class
- `projects` — cwd substring → default class (e.g. `cartesia-security` → implementor)

## Session env

| Var | Effect |
|---|---|
| `PI_PROFILE_CLASS` | Force class (`implementor`, `librarian`, `notetaker`, ...) |
| `PI_PROFILE_AGENT` / `PI_AGENT` | Resolve class from `agents` map |
| `/profile-class <name>` | Set class for this session |
| `profile_manifest` tool | Print the resolved row |

## Install

Add to `~/.pi/agent/settings.json` `packages`:

```
~/.pi/agent/local-packages/pi-profile-management
```

Restart pi. Existing sessions do not pick it up until reload.
