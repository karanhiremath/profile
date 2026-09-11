# Hermes tooling manager

Generic profile-level tooling for installing Hermes CLI packages and syncing a personal private Hermes workflow repo.

Data boundary:
- OK: generic install scripts, generic wrappers, personal non-work workflow scaffolds.
- Not OK: Cartesia-specific prompts, hosts, customer names, security findings, credentials, or internal runbooks.
- Work Hermes setup belongs in the Cartesia work repo.

## Commands

```bash
bin/hermes/install       # isolated tool install under ~/.local/share/hermes-toolchain
bin/hermes/install-tui   # isolated Bun runtime; herm shim -> local herm-tui fork
bin/hermes/configure-machine # machine-aware model/auth/config setup
bin/hermes/private-sync  # clone/update private personal repo
bin/hermes/doctor        # non-secret status
bin/hermes/env           # print PATH additions
bin/hermes/agents        # run isolated Hermes voice agents for daily terminal use
bin/hermes/cos           # launch personal Chief of Staff profile
bin/hermes/cos-s         # list/start cataloged personal sandboxes
bin/hermes/cosw          # launch work Chief of Staff profile
bin/hermes/dreamw        # launch work dreamer (host-native; prefers work-repo script; nighttide-work-dreamer)
bin/hermes/cosw-s        # list/start cataloged work sandboxes
bin/hermes/cosw-hostctl  # sandbox-safe client for CoS-W host project coordination
bin/hermes/pm <project>  # launch a registered project-manager TUI in the current pane
bin/hermes/pl <project>  # attach a registered project-lead implementation session
bin/hermes/notes-ledger  # deterministic two-ledger daily/review note capture
```

## Fleet steer (not tmux paste)

Live herm-tui / CoS-W / PM / PL panes are actuated by the private `atop` repo
(`just atop`), not by `tmux send-keys`, and **not by herdr**:

1. herm-tui always-on socket `$HERMES_HOME/steer-inbox/live/<pid>.sock`
2. Optional CONTROL HTTP (`CONTROL=1`)
3. Inbox JSONL is persistence only — a write is not delivery

Do not start `herdr server` for these fleets. Herdr hogs CPU. `hs` may still
launch herdr for personal sandboxes; that is a separate opt-in path.

```bash
atop steer --harness herm-tui --sid tmux:SESSION:WIN.PANE --mode nudge --text "..."
```


## CoS / PM / PL command model

These commands are generic profile-level wrappers. They do not embed work/private project state; they resolve profiles and project session registries from the normal Hermes search paths.

```bash
cos                         # agents up chief-of-staff (host-native)
cos --sandbox               # persist-attach to cos-sandbox-default
cos-s ls                    # list personal sandbox short names
cos-s cos                   # same as cos --sandbox
cos-s herm                  # start the personal herm TUI sandbox
cos-s dream                 # start the dream cockpit sandbox
dreamw                      # host-native work-dreamer; `dreamw --status` for inventory
cosw                        # host-native CoS-W (timeout-free cursor/grok-4.6:fast)
cosw --codex                # host-native CoS-W on openai-codex/gpt-5.5
cosw --xai-grok             # host-native CoS-W on xAI grok-4.6 (not Cursor SDK)
cosw --sandbox              # attach to the work-devboxes compose sandbox
cosw-s ls                   # list sandbox short names
cosw-s cosw                 # same as cosw --sandbox
cosw-s librarian            # agents up work-notes-librarian --sandbox
cosw --sandbox-stack list   # full catalog (includes host-only profiles)
pm <project>                # launch the Hermes PM TUI in the current pane
pl <project>                # attach the project-lead implementation tmux session
bin/hermes/project_sessions.py list
bin/hermes/project_sessions.py resolve <project>
```

### CoS-W launch planes

`cosw` defaults to **host-native** tools (`--host-tools` / local terminal). The
work-devboxes compose sandbox is opt-in (`cosw --sandbox` or `COSW_SANDBOX=1`).
The catalog lives in `~/src/karan.hiremath/agentic/hermes/sandboxes/catalog.yaml`.

Seats (launch-scoped; they do not rewrite the committed profile YAML lock):

- default / `--cursor-grok` — `cursor/grok-4.6:fast` with
  `PYTHONPATH` pinned at the timeout-free Cursor SDK worktree so the 180s
  nested-run bomb does not fire
- `--codex` / `--gpt-5.5` — `openai-codex/gpt-5.5` (ChatGPT Codex billing)
- `--xai-grok` — xAI `grok-4.6` (requires `XAI_API_KEY` or `hermes auth add xai-oauth`)

`cosw --print-plan` prints the resolved backend/seat and exits.

### CoS-W sandbox manager bridge

`cosw` still bootstraps a dedicated host-side manager before launching the
work CoS. When `--sandbox` is used, Hermes persist-attaches to
`cosw-sandbox-default` from the work-devboxes compose stack. The sandbox does
**not** receive the raw host tmux socket; it gets an allowlisted
`cosw-hostctl` client plus a private Unix socket. `COSW_COMPOSE=0` keeps the
older ad-hoc `podman run` smoke path.

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

The TUI installer downloads the Bun release asset for the current OS/arch, verifies it against `SHASUMS256.txt`, and installs it under the Hermes toolchain instead of using the global Bun installer. `herm` always execs the local fork (`~/src/herm-tui` or `~/src/herm` via `herm-fork-env.sh`), never published npm `herm-tui`. `just hermes` / `install` / `install-tui` / shell profile all rewrite `~/.local/bin/herm` to that checkout.

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
