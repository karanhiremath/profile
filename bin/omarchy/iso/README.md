# Omarchy ISO (home-mbp-13)

Default install for `home-mbp-13` (inventory name `khire-mbp-13`).
QEMU on `khire-mac-mini` boots the same artifact in tmux so we can test
it without the Try Omarchy.app HVF desktop.

## Artifacts

| Path | Role |
|------|------|
| `~/Library/Caches/hostctl/omarchy-4.0.3.iso` | Official bootstrap (pinned SHA256) |
| `~/.local/share/hostctl/omarchy/iso/current.iso` | What QEMU boots (symlink) |
| `~/.local/share/hostctl/omarchy/iso/custom/omarchy-home-mbp-13.iso` | Remaster output, when Arch build exists |
| `~/.local/share/hostctl/omarchy/cidata.iso` | Autoinstall overlay (hostname, keys) |
| `~/.local/share/hostctl/omarchy/disks/home-mbp-13.qcow2` | Install target / SD-card precursor |

Do not bake private keys or password hashes into git. Put
`OMARCHY_ISO_PASSWORD_HASH` in `~/.local/share/hostctl/omarchy.env`.

## Commands

```bash
hostctl omarchy iso fetch   # official 4.0.3 + sha256
hostctl omarchy iso build   # cidata + clone omacom/omarchy-iso
hostctl omarchy up          # qemu-system-x86_64 in tmux session oma-qemu
hostctl omarchy console     # tmux attach -t oma-qemu
hostctl omarchy bind        # host-owned SSH keys, no guest typing
```

## Custom remaster

`omarchy-iso-make` lives in [omacom/omarchy-iso](https://github.com/omacom/omarchy-iso)
and needs Arch. `iso build` clones `~/src/omarchy-iso` on `quattro` and
only runs the remaster when `/etc/arch-release` exists. On this Mac the
official ISO plus cidata is the working default until that builder exists.

Cidata is the Omarchy autoinstall second drive (`volid=cidata`):
`user_configuration.json`, optional `user_credentials.json`, and
`authorized_keys` from op-keychain. Missing credentials fall back to the
installer wizard.

## Physical install

The same `current.iso` (custom if present, else official) is what gets
written to the SD/USB for `home-mbp-13`. Do not use Try Omarchy.app.
