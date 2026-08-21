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
bin/hermes/cos           # launch personal Chief of Staff profile
bin/hermes/cosw          # launch work Chief of Staff profile
bin/hermes/cosw-hostctl  # sandbox-safe client for CoS-W host project coordination
bin/hermes/pm <project>  # attach/start a registered project-manager tmux/TUI
bin/hermes/pl <project>  # attach a registered project-lead implementation session
bin/hermes/notes-ledger  # deterministic two-ledger daily/review note capture
```

## CoS / PM / PL command model

These commands are generic profile-level wrappers. They do not embed work/private project state; they resolve profiles and project session registries from the normal Hermes search paths.

```bash
cos                         # agents up chief-of-staff
cosw                        # agents up chief-of-staff-work
pm <project>                # attach/start the Hermes PM TUI session for project
pl <project>                # attach the project-lead implementation tmux session
bin/hermes/project_sessions.py list
bin/hermes/project_sessions.py resolve <project>
```

### CoS-W sandbox manager bridge

`cosw` bootstraps a dedicated host-side sandbox manager before launching the
work CoS. The Docker sandbox does **not** receive the raw host tmux socket;
instead it gets an allowlisted `cosw-hostctl` client plus a private Unix socket.

```bash
cosw --dispatch-doctor
cosw-hostctl bootstrap
cosw-hostctl fleet-status
cosw-hostctl status <project>
cosw-hostctl ensure-pm <project>
cosw-hostctl dispatch-pm <project> --message 'PM ACTION REQUIRED: ...' --handoff /absolute/path --wait-ack 120
```

Allowed bridge actions are project-registry driven: ensure PM/PL sessions,
append registered non-secret project-bus events, dispatch PM action requests,
and check dispatch acknowledgement. Project names, tmux sessions, writable bus
paths, and PM profiles come from the project registry, not from sandbox guesses.

## Notes ledger capture

`notes-ledger` is the first deterministic layer for CoS note-taking. It can
create daily notes, ingest bounded work/personal capture packets, emit only the
sanitized work-load signal across ledgers, generate weekly/monthly review notes,
and detect optional local inference providers.

```bash
bin/hermes/notes-ledger schema
bin/hermes/notes-ledger create-daily --ledger personal
bin/hermes/notes-ledger capture --ledger personal --packet <personal-packet.yaml>
bin/hermes/notes-ledger emit-work-signal --packet <work-packet.yaml>
bin/hermes/notes-ledger index --ledger work --write
bin/hermes/notes-ledger rollup --ledger work --cadence weekly --write
bin/hermes/notes-ledger-fixture-test
```

Stdout is JSON only. Optional inference is local-only, off by default, and
falls back to deterministic templates when unavailable.

Project registries are searched in:

1. `$HERMES_PROJECT_REGISTRY_PATH` / `$HERMES_PROJECT_REGISTRY_DIRS`
2. `~/src/karan.hiremath/agentic/hermes/projects`
3. `~/src/hermes/projects`
4. `bin/hermes/projects`

A PM-managed handoff is incomplete unless the project event bus receives a `pm_action_required` event telling the PM to register/spawn the replacement Pi coding agent with the handoff prompt. Profile owns the wrappers; project-specific event types, handoffs, kanban/Linear references, and guardrails live in the project registry.

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
- pnpm home: `<toolchain>/pnpm` (global bin, global-dir, and store all scoped here via `PNPM_HOME`)
- Python venv: `<toolchain>/venv`
- Bun runtime: `<toolchain>/bun`
- private repo: `git@github.com:karanhiremath/hermes.git`
- private checkout: `$HOME/src/hermes`

The installer uses `uv venv`, installs the small Python helper dependency (`PyYAML`), and prepends the venv to `PATH` while running pnpm so package lifecycle Python installs land in the Hermes toolchain venv, not system Python. Node itself is supplied by mise; only the Hermes packages are installed into the isolated pnpm global.

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
