# Hermes tooling manager

Generic profile-level tooling for installing Hermes CLI packages and syncing a personal private Hermes workflow repo.

Data boundary:
- OK: generic install scripts, generic wrappers, personal non-work workflow scaffolds.
- Not OK: Cartesia-specific prompts, hosts, customer names, security findings, credentials, or internal runbooks.
- Work Hermes setup belongs in the Cartesia work repo.

## Commands

```bash
bin/hermes/install       # isolated tool install under ~/.local/share/hermes-toolchain
bin/hermes/install-tui   # isolated Bun runtime for herm TUI
bin/hermes/private-sync  # clone/update private personal repo
bin/hermes/doctor        # non-secret status
bin/hermes/env           # print PATH additions
```

Defaults:
- toolchain: `${XDG_DATA_HOME:-$HOME/.local/share}/hermes-toolchain`
- npm prefix: `<toolchain>/npm`
- Python venv: `<toolchain>/venv`
- Bun runtime: `<toolchain>/bun`
- private repo: `git@github.com:karanhiremath/hermes.git`
- private checkout: `$HOME/src/hermes`

The installer uses `uv venv` and prepends the venv to `PATH` while running npm so package lifecycle Python installs land in the Hermes toolchain venv, not system Python.

The TUI installer downloads the Bun release asset for the current OS/arch, verifies it against `SHASUMS256.txt`, and installs it under the Hermes toolchain instead of using the global Bun installer.
