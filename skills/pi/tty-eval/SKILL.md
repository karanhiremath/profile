---
name: tty-eval
description: Capture a command's screen on a real PTY (or QEMU console). Never Cos send-keys. Use for agent eval of nvim/telescope/TUI frames and host TTY inventory.
---

# tty-eval

PTY capture for agent eval. Does not attach or send-keys to Cos / CosW / live atop panes.

## Commands

```
atop tty --probe
atop tty --settle-ms 400 -- python3 -c 'import os; print(os.isatty(0))'
atop tty --plain --out /tmp/frame.txt -- atop vi
atop vi tty
```

- `--probe` — host TTY + QEMU/UTM/Lima/SSH:2222 inventory (JSON, schema `atop.tty-eval.probe.v1`)
- `--mode pty` — local PTY (default)
- `--mode qemu` — guest via `ssh -t 127.0.0.1:2222`
- `--plain` — strip CSI/OSC

Binary: `bin/atop/tty-eval` (dispatched by `bin/a-top tty`). Smoke: `bin/atop/test_tty_eval.sh`.

Skill directory: this file's parent.
