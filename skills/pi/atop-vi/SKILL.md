---
name: atop-vi
description: Open a new nvim + telescope over prompt buffers from every harness. Use `atop vi`. Never send-keys.
---

# atop-vi

```
atop vi                  # new nvim coordinator buffer + telescope
a-top vi                 # same
~/src/profile/bin/atop/vi
atop vi list             # herm / pi / claude / codex / cursor / workbench / tmp
atop vi <id> get
atop vi <id> set --file PACKET.md   # queued job JSON (default)
atop vi <id> set --wait --file PACKET.md
aos buf catalog|get|set|apply|jobs  # rust primitive (aos-buf)
aos apply <id> --file PACKET.md     # aos.apply.v1
atop vi jobs / atop vi job <id>
atop vi tty              # PTY frame dump for agent eval
atop tty --probe         # QEMU / UTM / Lima / 127.0.0.1:2222
```

Default opens a **new** nvim (not the target harness editor). `open` `--listen`s and edits `$TMPDIR/atop-vi.$USER.md`. Telescope lists live sockets and on-disk temps. `<CR>` `:edit`s that prompt file. `<leader>fv` reopens the menu. Ghostty is outer host only — nvim execs in the current TTY. Coordinate with `atop vi atop-vi get|set`, never send-keys. `set` is backgrounded by default so a blocked nvim `:write` does not stall the agent; poll `atop vi job <id>` or pass `--wait` only when this turn must block.

Related: `a-top`.
