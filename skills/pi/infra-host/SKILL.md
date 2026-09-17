---
name: infra-host
description: Cross-host and sandbox tmux attach via tmux-connect, tc, and tc-s. Registry aliases only.
---

# infra-host

Host registry: `~/src/profile/bin/tmux/hosts/registry.conf`
(plus extra registries via `TMUX_CONNECT_EXTRA_REGISTRIES`).

Canonical tool: `~/src/profile/bin/tmux/tmux-connect`.
Work aliases: `~/src/karan.hiremath/scripts/shell-ext.sh`.

Codex tool shells may not load zsh profile aliases. For noninteractive tool
calls that need `tc` or `tc-s`, use this preamble:

```
export PROFILE_DIR=/Users/karanhiremath/src/profile
export KH_DIR=/Users/karanhiremath/src/karan.hiremath
source /Users/karanhiremath/src/karan.hiremath/scripts/shell-ext.sh
```

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
tc 2                         # cxis-devlarge-2, tmux session home
tc 2 cosw-codex              # cxis-devlarge-2, named host tmux session
tc 2 --ls                    # list host tmux sessions
tc-s 2 --ls                  # list rootless podman sandboxes on tc2
tc-s 2 <sandbox>             # tmux session home inside sandbox
tc-s 2 <sandbox> <session>   # named tmux session inside sandbox
tc-s 2 <sandbox> --ls        # list tmux sessions inside sandbox
mac                          # local tmux (default session mac)
```

Use `--ls` probes first in automation. Attach only when the user asked for an
interactive session. Future host families should follow this same
registry-backed `tmux-connect` pattern instead of one-off SSH variants.

`harness-sync pull home-mac-mini` — personal-safe toolkit only.
`harness-sync pull --all tc2` — explicit, any class.

Never read or write `auth.json`. Personal hosts must not pull work packages.
