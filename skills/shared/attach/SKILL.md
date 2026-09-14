---
name: attach
description: "Default host/sandbox-agnostic attach SOP for agentic sessions. Use mac / oma / <kind>-<instance> / trailing -s to open tmux. Do not bind from a guest terminal."
user-invocable: true
argument-hint: "mac|oma|oma-default|mac-s|oma-s [session]"
---

# Attach SOP

This is the default way to open a working session on any machine that has
profile. It is host-agnostic and sandbox-agnostic. Do not invent per-agent
tmux or SSH wrappers.

## Grammar

```text
<kind>[-<instance>][-s] [--instance NAME] [--session NAME] [--family NAME] [session]
```

| Form | Meaning |
|------|---------|
| `mac` | Host tmux on a macOS host (default session `mac`) |
| `oma` / `oma-default` | Omarchy instance titled `default`, session `home` |
| `oma-default cos` | Same instance, session `cos` |
| `oma-s` / `oma-default-s` | Podman sandbox tmux on that Omarchy instance |
| `mac-s` / `mac-s notes` | Isolated podman sandbox on this host |

Trailing `-s` is the sandbox marker. There is no `sorroma` alias.

## Rules

1. Prefer Tailscale FQDNs; QEMU `127.0.0.1:2222` is fallback only.
2. Keys come from `hauth unwrap-or-get <alias>` when `HAUTH_SVID` is set,
   otherwise `op-keychain get <alias>`. Never `op read` or guest-terminal paste.
3. After an Omarchy factory reset, run `hostctl omarchy bind` on the **host**.
   Do not ask the user to type commands in the qemu curses window.
4. `*-s` sandboxes default to `nixos` (Nix flakes + Devbox, SELinux from the
   Podman machine). Language overlays: rust, elixir, mojo, go, python. Distrohop
   later uses the same contract via Devbox and mise. Never default to ubuntu.
   Node is opt-in (`--family node-web`, pnpm + Vite).
5. Inventory lives in `bin/hostctl/interactive.yaml`. Add instances there;
   do not hard-code hosts in agent prompts.

## Commands

```bash
attach oma-default
attach oma-default cos
attach mac-s sandbox-test
attach mac-s --family rust notes
hostctl omarchy bind
hostctl sandbox family --kind mac --instance default --session notes
```

Skill directory: this file's parent.
