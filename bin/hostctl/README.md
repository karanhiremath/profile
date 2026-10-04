# hostctl

Personal host control plane for stacks on this Mac mini.

This is **not** `cosw-hostctl`. That client talks to the work CoS sandbox host
bridge. This `hostctl` owns host-level labs on `khire-mac-mini`.

## Stacks

| Stack | Kind | Status |
|-------|------|--------|
| `termix` | compose + Tailscale Serve | **termix-master** |
| `omarchy` | qemu-system-x86_64 in tmux (`oma-qemu`) + Omarchy ISO | enabled |

Termix and Omarchy do not share a compose file, a port, or Serve.
Omarchy is the official ISO (bootstrap) plus a custom remaster for
`home-mbp-13` / `khire-mbp-13`, booted under QEMU. Not Try Omarchy.app,
not a Podman image, and not an Asahi dual-boot. Termix stays tailnet-only
with its own login.

## Commands

```bash
just hostctl                 # link ~/.local/bin/hostctl
hostctl status               # machine + termix + omarchy
hostctl up                   # start Termix + Serve (does not launch Omarchy)
hostctl down                 # stop Termix compose
hostctl termix status
hostctl termix snippets      # upsert unfiled Termix snippets for live sessions
hostctl omarchy up           # fetch ISO if needed, start QEMU in tmux
hostctl omarchy console      # tmux attach -t oma-qemu
hostctl omarchy iso fetch    # official 4.0.3 bootstrap
hostctl omarchy iso build    # cidata + clone omarchy-iso
hostctl omarchy status
hostctl omarchy ports        # Termix / SSH / mosh forward recipe
hostctl omarchy setup-ssh    # op-keychain public keys + ssh config Host try-omarchy
hostctl omarchy bind         # post-reset: keys, guest helpers, Termix try-omarchy
hostctl omarchy ssh          # ssh -p 2222 karan@127.0.0.1
hostctl omarchy down
hostctl omarchy destroy      # stop QEMU; remove leftover Try Omarchy.app
hostctl role                 # this host is termix-master
hostctl hosts                # tailnet inventory (master / limited / isolated)
hostctl master provision     # restricted hostctl SSH key for this Termix pod
hostctl master push          # push that key into Termix via the CLI
hostctl master login         # push the interactive login key from op-keychain
hostctl master keychain-seed # seed Termix SSH keys into op-keychain
```

Attach aliases (`mac` / `oma` / `oma-default` / `mac-s` / `oma-s`) use the
host/sandbox-agnostic grammar in `bin/hostctl/interactive.yaml` and
`bin/tmux/interactive`. Keys come from `hauth unwrap-or-get` when `HAUTH_SVID`
is set, else `op-keychain get` — never `op read`.
Phone-facing shortcuts: `termix <session>` / `phone <session>` for host tmux,
`termix-s` / `phone-s` for the host sandbox. There is no `sorroma` alias.

## termix-master

This Mac runs the one Termix pod for the tailnet. Isolated sandboxes are not
second Termix pods on Serve; they stay off this key and off the master
inventory until an ACL says otherwise.

`hostctl master provision` installs a dedicated ed25519 key whose
`authorized_keys` line can run `hostctl` allowlisted commands only. It cannot
open a login shell. Import that key in the Termix UI from this Mac.

## Omarchy

The guest on this M4 Pro is `qemu-system-x86_64` (TCG) in tmux session
`oma-qemu`. The official Omarchy 4.0.3 ISO is bootstrap only. The default
install for `home-mbp-13` (inventory `khire-mbp-13`) is the custom remaster
plus cidata overlay under `bin/omarchy/iso/`.

`hostctl omarchy up` fetches the bootstrap ISO if needed and starts QEMU.
Guest SSH is `karan@127.0.0.1:2222` via user-net hostfwd. After a factory
reset run `hostctl omarchy bind` on the **host** (never the qemu curses
window): it publishes `op-keychain` public keys onto `~/src/.omarchy-host`,
drops `bind-guest.sh` / `fix-sshd.sh`, upserts `Host try-omarchy` plus the
tailnet FQDN in `~/.ssh/config`, probes `:2222`, tries QMP guest-exec when
sshd is down, and upserts the Termix host `try-omarchy` at
`host.containers.internal:2222`.
Do not bake those keys into a factory image. Optional vault sync is
`OMARCHY_SYNC_OP_VAULT=1` only.

Do not:

- add Omarchy to the Termix compose
- put it on Tailscale Serve or Funnel
- run `sandbox-ctl --family omarchy-desktop rebuild`
- dual-boot this mini (Omarchy M installer targets M1/M2)
- reinstall Try Omarchy.app
