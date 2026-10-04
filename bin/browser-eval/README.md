# browser-eval

Generic security-validation lab for agentic browsers. Sibling of
`bin/herdr/harness-lab`. Keep Cartesia-specific findings in the work ledger.

This is **not** a daily-browser installer. Arc stays the human browser.
**Temporary exception:** signed-in Google Chrome Default may be *opened*
for Perplexity only (`launch perplexity`). Do not CDP-attach that profile
and do not use it for Dia/Comet/OSS eval. Arc stays no-CDP.

## Lanes

| Lane | Role | Where it runs |
|------|------|----------------|
| `perplexity` | signed-in Chrome Default, Perplexity only | host open; no CDP |
| `chrome-compat` | Chromium engine via isolated Chrome `--user-data-dir` | host eval profile only |
| `arc` | primary human browser | catalog / no-CDP |
| `dia` | agentic-first eval (macOS Apple Silicon) | `~/.local/share/browser-eval/apps/Dia.app` |
| `comet` | agentic-first eval (macOS) | `~/.local/share/browser-eval/apps/Comet.app` |
| `oss` | Chromium, Firefox ESR, Playwright Chromium, `browser-use` backup | rootless Podman |
| `omarchy` | Linux guest probe (Chromium/Firefox only) | QEMU `oma-qemu` |

Dia and Comet have no Linux builds. Omarchy tests OSS browsers only.

## Policy

- Install Dia/Comet under the eval state dir, never `/Applications`.
- Isolated `--user-data-dir` under `~/.local/share/browser-eval/profiles`.
- CDP binds `127.0.0.1` only. Distinct ports per target.
- Do not mount `~/.ssh`, 1Password, cloud configs, or host browser profiles.
- `browser-use` is a backup driver, installed in the lab image / eval venv.
- `pi-browser-harness` may attach only to an eval-scoped Chromium/Chrome-compat
  window. Native `/browser-setup` still happens in a pi TUI.
- Perplexity recovery uses signed-in Chrome Default until a dedicated session
  exists. Subagents own Dia/Comet install, Podman OSS, and Omarchy after
  `just browser-eval preflight` passes.
- Do not start `herdr server` from inside a Herdr/Pi pane.

## Commands

```bash
just browser-eval preflight
just browser-eval install-host-apps
just browser-eval validate
just browser-eval build
just browser-eval smoke
just browser-eval omarchy-probe
bin/browser-eval/scripts/launch perplexity
bin/browser-eval/scripts/launch chrome-compat
bin/browser-eval/scripts/launch dia
bin/browser-eval/scripts/launch comet
```

## Promotion

A browser or driver is not eval-ready until `scripts/validate` writes a pass
artifact covering: isolated profile, localhost CDP, no host-secret mounts,
codesign/assess (macOS), and no CDP attach to Arc or Chrome Default.
Perplexity-in-signed-in-Chrome is an open-only exception, not eval-ready.
