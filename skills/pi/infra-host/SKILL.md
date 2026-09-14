---
name: infra-host
description: Cross-host tmux/ssh attach for home-mac-mini and tc2. Registry aliases only.
---

# infra-host

Host registry: `~/src/profile/bin/tmux/hosts/registry.conf`
(plus extra registries via `TMUX_CONNECT_EXTRA_REGISTRIES`).

| alias | host |
|---|---|
| mini | home-mac-mini |
| tc2 | cxis-devlarge-2 |
| mac / local | this workstation |

## Commands

```
tmux-connect                 # fzf picker
tmux-connect mini            # home-mac-mini, default session
tmux-connect tc2             # work large host, if registered
tmux-connect --ls mini       # list remote sessions
mac                          # local tmux (default session mac)
```

`harness-sync pull home-mac-mini` — personal-safe toolkit only.
`harness-sync pull --all tc2` — explicit, any class.

Never read or write `auth.json`. Personal hosts must not pull work packages.
