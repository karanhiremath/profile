---
name: infra-host
description: Cross-host tmux/ssh attach for home-mac-mini, this MBP, and tc2. Aliases and registry only; no Cartesia facts.
---

# infra-host

Host registry: `~/src/profile/bin/tmux/hosts/registry.conf`

| alias | host |
|---|---|
| mini | home-mac-mini |
| tc2 | cxis-devlarge-2 |
| mac | this workstation |

## Commands

- `tmux-connect` / `tc <n> <session>`
- `harness-sync pull home-mac-mini` — personal-safe toolkit only
- `harness-sync pull --all tc2` — explicit, any class

Never read or write auth.json. Personal hosts must not pull work packages.
