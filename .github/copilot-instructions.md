# Copilot Instructions

## What this repo is

A personal developer environment configuration repository. Running `./install.sh` symlinks config files and installs tools (zsh, tmux, nvim, git, etc.) to set up a full dev environment. Works on macOS and Linux (Ubuntu, Debian, RHEL8, NixOS, Alpine).

## Build & Install Commands

```bash
# Full install (bootstraps everything)
./install.sh

# Install a specific app
just tmux
just nvim
just git

# macOS full setup
just mac
```

## Testing

Tests run installations inside containers (Podman preferred, Docker fallback).

```bash
# Run all OS variants
just test
# or: ./bin/test/run-tests.sh all

# Test a single OS
just test-ubuntu
./bin/test/run-tests.sh debian

# Test a specific app on a specific OS
./bin/test/run-tests.sh -a tmux ubuntu

# Verbose output
./bin/test/run-tests.sh -v ubuntu

# Keep containers after test (for debugging)
./bin/test/run-tests.sh -k ubuntu

# Validate specific apps are installed correctly
./bin/test/validate-apps.sh git tmux vim
```

## Architecture

- `install.sh` — main entrypoint; sources `bin/sh/shell_fns`, runs `just all`, then `just mac` on macOS
- `bin/<app>/install` — one install script per tool; most follow the template in `bin/template/install.sh`
- `bin/sh/shell_fns` — shared shell library sourced by all install scripts (see Key Conventions)
- `myprofile.sh` / `zsh_profile.sh` / `bash_profile.sh` — shell aliases, functions, environment vars
- `bin/test/` — container-based test infrastructure with per-OS Dockerfiles and a shared `config.sh`
- `Justfile` — task runner wrapping install scripts and test commands

## Key Conventions

### Install script pattern

Every `bin/<app>/install` script follows this pattern (see `bin/template/install.sh`):

```bash
#!/bin/bash
set -euo pipefail
shopt -s failglob

. "${PROFILE_DIR}"/bin/sh/shell_fns --source-only

app_name="myapp"
MACHINE="$(uname -s)"   # Darwin | Linux
ARCH="$(uname -m)"      # x86_64 | aarch64

# Check if already installed first (idempotent)
if command -v "$app_name" >/dev/null 2>&1; then
    echo "Already installed!"
else
    install_messages "start" "$app_name"
    case "${MACHINE}" in
        Linux)  ...;;
        Darwin) ...;;
    esac
    install_messages "end" "$app_name"
fi
```

### Shared shell library (`bin/sh/shell_fns`)

Key functions available in all install scripts:
- `install_app <name>` — installs `bin/<name>/install`, or runs `bin/<name>/update` if already present
- `cmd_test_or_install <name>` — returns 0 if command exists, 1 otherwise
- `install_messages start|end <name>` — prints timestamped start/end banners to stderr
- `generate_config_vars` — detects `$MACHINE` / `$ARCH`, writes to `~/.config/.vars`

### Environment variables expected by install scripts

- `PROFILE_DIR` — absolute path to repo root (set by `install.sh` and `Justfile`)
- `APP_BIN` — `${PROFILE_DIR}/bin` (set alongside `PROFILE_DIR`)

### Adding a new app

1. Copy `bin/template/install.sh` to `bin/<appname>/install`
2. Add a recipe to `Justfile` calling `./bin/<appname>/install`
3. Add the recipe to the `all` recipe in `Justfile` if it should run by default
4. Optionally add `bin/<appname>/update` for upgrade logic

### Container testing

`bin/test/config.sh` auto-detects Podman or Docker (`CONTAINER_ENGINE`). Each OS has its own `Dockerfile.<os>`. Tests run as an unprivileged `testuser` with passwordless sudo inside the container.
