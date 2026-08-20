# Profile — Dev Tooling & Dotfiles

Personal development environment setup for Karan Hiremath. Shared across work and personal machines.

## What's Here

| Path | Purpose |
|------|---------|
| `bin/` | Tool installers (each tool gets `bin/<tool>/install`) |
| `myprofile.sh` | Shell aliases & functions (sourced by zsh/bash) |
| `zsh_profile.sh` / `bash_profile.sh` | Shell-specific config |
| `.tmux.conf` | Tmux configuration |
| `Justfile` | Task runner — `just <tool>` to install any tool |
| `install.sh` | Full bootstrap script |
| `.claude/commands/` | Claude Code custom commands |

## Inference & Sandboxes

| Path | Purpose |
|------|---------|
| `config/inference/backends.toml` | every inference backend, local + hosted |
| `bin/inference/inf` | resolve, probe, bench, and bind backends into harnesses |
| `config/sandbox/sandboxes.toml` | project sandbox specs |
| `bin/sandbox/sbx` | lease-gated sandbox lifecycle + audit |
| `bin/agent-loop/loop` | 30m backlog dispatch to coding agents |
| `docs/local-model-testing.md` | operator SOP |
| `config/inference/SCHEMA.md` | registry field reference and validator rationale |

A harness must never hardcode a provider/model pair — declare the backend once
and bind it (`inf bind <harness> <id>`). Never commit a secret value to a
registry: they hold env var *names*. Work-only entries go in the work overlay
(`~/src/karan.hiremath/agentic/`), and `validate` enforces that boundary.

## Conventions

### Adding Tools
- Every tool lives in `bin/<tool-name>/install`
- Install script must be `chmod +x`, use `set -euo pipefail`, support `--help`
- Add a corresponding Justfile recipe
- Use the `.claude/commands/add-tool.md` command when adding via Claude Code

### Justfile Pattern
```just
tool-name:
    #!/usr/bin/env bash
    set -euo pipefail
    export PROFILE_DIR="$(pwd)"
    export APP_BIN="${PROFILE_DIR}/bin"
    ./bin/tool-name/install
```

### Shell Functions
- Short git aliases: `gb`, `gac`, `gacp`, `gs`
- Tmux: `mac`, `local_tmux`, `tl` (load), `ts` (save)
- Navigation: `profile` → cd to this repo

## Related Repos
- Personal notes & dailies: `~/src/notes`
- Work context & agent fleet: `~/src/karan.hiremath` (Cartesia only)

## No Project Context Here
This repo is purely tooling. Project-specific memory, notes, and decisions live in `notes` (personal) or `karan.hiremath` (work).
