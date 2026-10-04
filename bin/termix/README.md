# Termix wrappers

Start the local Termix container and publish it on the tailnet with Tailscale
Serve. This pod is **termix-master**: one Termix for the tailnet, with a
restricted `hostctl` key on this host. Termix already has its own login, so
it stays tailnet-only. Isolated hosts are inventory + ACL, not this key.

Public internet + Google OIDC is a separate edge for other resources:
`~/src/krop-infra/infra/edge/apps` (`https://apps.krop.ai`). Funnel stays off.

## Endpoints

| Path | URL |
|------|-----|
| Loopback | `http://127.0.0.1:8080` |
| Tailnet Serve | `https://<this-node>.tail1e8436.ts.net` |
| Pretty name | `https://termix.krop.ai:8444` (internal Caddy; `termix-up caddy`) |
| Public Termix | none |
| Public apps edge | `https://apps.krop.ai` (SSO scaffold, no backends yet) |

## Commands

```bash
just termix          # install official CLI + link wrappers
termix-up            # compose up, health check, provision Serve
termix serve         # provision Serve only
termix-up caddy      # termix.krop.ai:8444 pretty name (not host.containers.internal)
termix status        # local / tailnet
termix login         # official CLI against the tailnet URL
termix cos           # attach host tmux session `cos` (same as attach mac cos)
termix --ls          # list host tmux sessions
termix-s notes       # attach host sandbox (same as attach mac-s notes)
termix snippets-sync # upsert Termix snippets for every live tmux session
```

Phone snippets are **unfiled** (no folder) so the iOS keyboard dock and
home-screen widget can see them. Session snippets are the zsh command
(`cos`, `mac`, `phone-s`). Key snippets send the real keys: `ctrl-g`,
`panes` (tmux `C-a q`), `zoom` (`C-a z`), `esc`, `wq` / `w` / `q` /
`q!`, and `palette` (`:Telescope commands`). The Termix keyboard
appends Enter after every snippet. After sync, open **Settings →
Snippets** on the phone to republish the widget snapshot.

The wrapper never runs `tailscale funnel`. If Funnel is already enabled, Serve
provisioning fails closed.

If the tailnet has Serve disabled, `termix-up` prints the Tailscale enable URL
and exits instead of waiting on an interactive login.

## Environment

| Variable | Default |
|----------|---------|
| `TERMIX_COMPOSE_DIR` | `~/Documents/Codex/2026-09-11/start-claude-cli-remote-control` |
| `TERMIX_LOCAL_URL` | `http://127.0.0.1:8080` |
| `TERMIX_SERVE_PROXY` | `http://127.0.0.1:8080` |
| `TERMIX_SERVE_HTTPS_PORT` | `443` |
| `TERMIX_SERVE_FORCE` | `0` (set `1` to replace a conflicting Serve config) |
| `TERMIX_SKIP_SERVE` | `0` |
| `TERMIX_CLI` | resolved official CLI path |
