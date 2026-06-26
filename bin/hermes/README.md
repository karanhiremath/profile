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
bin/hermes/configure-machine # machine-aware model/auth/config setup
bin/hermes/private-sync  # clone/update private personal repo
bin/hermes/doctor        # non-secret status
bin/hermes/env           # print PATH additions
bin/hermes/agents        # run isolated Hermes voice agents for daily terminal use
```

## Voice agents (`agents`)

Run isolated Hermes voice agents (each in its own `HERMES_HOME`) wired to the
Cartesia TTS/STT plugin (`plugins/cartesia/`) for day-to-day terminal / tmux /
TUI (and messaging) workflows. Each profile picks an endpoint and voice; bring
one up as a CLI, TUI, or messaging gateway.

```bash
bin/hermes/agents list                 # profiles, surface, endpoint, home status
bin/hermes/agents resolve staging-voice # show resolved config (internal host redacted)
bin/hermes/agents check staging-voice   # materialize + end-to-end endpoint health check
bin/hermes/agents up staging-voice                      # launch (profile's default surface)
bin/hermes/agents up staging-voice --surface tui
bin/hermes/agents up staging-voice --surface gateway --platform telegram --check
bin/hermes/agents new my-voice          # scaffold profiles/my-voice.yaml from TEMPLATE
```

- Profiles are loaded from a search **path** (first match wins), so each profile
  lives where it belongs:
  - `work` → `~/src/karan.hiremath/agentic/hermes/profiles/` (internal Cartesia validation)
  - `personal` → `~/src/hermes/profiles/` (public/personal)
  - `profile` → `bin/hermes/profiles/` (this repo — generic `TEMPLATE` only)
  Override the whole path with `HERMES_AGENT_PROFILE_PATH` (os.pathsep-separated).
  Create into a specific repo: `agents new <name> --dir work|personal|profile|<path>`.
- Isolated homes live under `${XDG_DATA_HOME:-~/.local/share}/hermes-validation/<profile>/`.
- Secrets: `CARTESIA_API_KEY` (+ internal endpoint hosts like
  `CARTESIA_STAGING_URL`) live in machine-local `~/.hermes/.env`, never here.
  Homes derive their `.env` from it; gateway platform tokens set per-home survive.

Defaults:
- toolchain: `${XDG_DATA_HOME:-$HOME/.local/share}/hermes-toolchain`
- npm prefix: `<toolchain>/npm`
- Python venv: `<toolchain>/venv`
- Bun runtime: `<toolchain>/bun`
- private repo: `git@github.com:karanhiremath/hermes.git`
- private checkout: `$HOME/src/hermes`

The installer uses `uv venv` and prepends the venv to `PATH` while running npm so package lifecycle Python installs land in the Hermes toolchain venv, not system Python.

The TUI installer downloads the Bun release asset for the current OS/arch, verifies it against `SHASUMS256.txt`, and installs it under the Hermes toolchain instead of using the global Bun installer.

`install` writes user-local shims to `${HERMES_SHIM_DIR:-$HOME/.local/bin}` for `hermes`, `hermes-agent`, and `herm`. If that directory is already on PATH, no `source <(.../env)` step is needed.

## Machine-aware setup

`configure-machine` reads a non-secret profile from:

```text
${HERMES_PRIVATE_DIR:-$HOME/src/hermes}/machines/${HERMES_MACHINE_PROFILE:-$(hostname -s)}/hermes.yaml
```

Example profile:

```yaml
model:
  provider: openai-codex
  default: gpt-5.5
  base_url: https://chatgpt.com/backend-api/codex
auth:
  import_codex_cli: true
```

Ansible entrypoint:

```bash
ansible-playbook -i <inventory> <profile_repo>/bin/hermes/ansible/hermes.yml
```
