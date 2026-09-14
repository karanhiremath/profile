---
name: atop-vi
description: Open a new nvim + telescope over prompt buffers from every harness. Use `atop vi`. Never send-keys.
---

# atop-vi

```
atop live                # sessions + AOS layer strip (text)
atop vi                  # live dashboard + telescope (sessions first)
a-top vi                 # same
~/src/profile/bin/atop/vi
atop vi list             # session/prompt catalog
atop vi <id> get
atop vi <id> set --file PACKET.md
atop vi tty              # PTY frame dump for agent eval
atop tty --probe         # QEMU / UTM / Lima / 127.0.0.1:2222
```

Default opens a **new** nvim. Coordinator buffer is a live AOS/session dashboard (`atop.live.v1`). Telescope lists live sessions (state/activity) then prompt buffers. Session preview is `tmux capture-pane`. `<CR>` `:edit`s a prompt file. `<leader>fv` / `<C-r>` refresh. Coordinate with `atop vi atop-vi get|set`, never send-keys.

Related: `a-top`.
