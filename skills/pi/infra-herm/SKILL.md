---
name: infra-herm
description: Host/gateway overlay pin — fork-env.sh, HERMES_AGENT_ROOT, Cursor provider registry, TUI persist. Do not kill live Cos panes.
---

# infra-herm

Pin the Hermes gateway to the overlay so Cursor (and grok-4.6 / grok-4.6:fast) register.

## Pin

Export via `~/src/profile/bin/hermes/fork-env.sh`:

- `HERMES_AGENT_ROOT` → overlay (not stock `~/.hermes/hermes-agent`)
- `HERMES_PYTHON` → overlay interpreter

If a live Cos/herm-tui pane started before the pin, **restart that pane**. Do not kill it from an agent.

## Persist

TUI-owned `config.yaml` keys and `herm/tui.json` theme survive `agents up` unless `HERMES_AGENT_FORCE_CONFIG=1`. Theme pins use `nighttideDefault`. Pin-aware theme apply: `apply-nighttide-theme --set-default`. Do not run the old remapper.

## Tests

- `bin/hermes/test_fork_env.sh`
- `bin/hermes/test_hermes_agents_persist.py`
- `bin/hermes/test_apply_nighttide_theme.py`

## Not this skill

- Nighttide colors → `herm-tui-profiles`
- Attach SOP → `attach`
- Isolated-home skill links → `aos`
