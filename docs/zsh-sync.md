# zsh-sync — cross-host zsh defaults with a merge queue

Keeps zsh defaults identical across hosts and sandboxes with minimal drift.

## Layout contract (see `zshrc.bootstrap`)

| Path | Role | Synced |
|---|---|---|
| `<profile>/zsh_profile.sh`, `myprofile.sh` | shared defaults/functions | yes (git) |
| `<profile>/zsh.d/*.zsh` | shared ordered fragments | yes (git) |
| `~/.zshrc` | thin bootstrap (copy of `zshrc.bootstrap`) | refreshed by install |
| `~/.zshrc.d/*.zsh` | host-local fragments | **never** |
| `~/.zshrc.secrets` | secrets, 0600 | **never** |
| `~/.pi/agent/bin/pi-update-wrapper.sh` | pi pre-launch update fn | refreshed by install |
| `~/.local/bin/doctor` | hermes toolchain doctor shim | refreshed by install |

Hosts source shared fragments directly from the profile checkout, so
`sync` = git pull + reinstall managed copies. Host-specific content goes in
`~/.zshrc.d/`, secrets in `~/.zshrc.secrets` — never in `~/.zshrc`.

## Commands (`bin/zsh/zsh-sync`)

- `status [--json]` — drift report (repo checkout, installed copies, host fragments) + queue state.
- `capture [--dry-run]` — convert drift into queue items under `merge-queue/pending/`.
  Refuses (exit 3) anything that looks like a credential; move it to `~/.zshrc.secrets`.
- `push` — publish pending items to the `zsh-queue` branch (temp worktree, no working-tree churn).
- `merge [--all | <id>]` — integrator: apply reviewed items, `zsh -n` / `bash -n` validate,
  one commit per item, move to `merge-queue/merged/`.
- `sync` — `git pull --ff-only` + rerun `bin/zsh/install` + report.
- `migrate` — adopt an unmanaged `~/.zshrc`: backup, strip profile-source lines into
  `~/.zshrc.d/00-migrated-*.zsh`, install bootstrap. Warns on secret-like lines (does not move them).

## Flow

drift (sandbox/host edit) → `capture` → `push` → integrator `merge` → `git push` →
`sync` on every other host. Sandboxes: run `bin/zsh/install` once, work in
`~/.zshrc.d/`, then `capture` + `push`.

## Sandbox note

macOS direct-exec runs scripts with `/bin/bash` (3.2): a failed `.` builtin is fatal
there even under `|| true`. Installers guard sourced helpers with existence checks —
keep that pattern for any new installer.

## Startup work

The bootstrap loads shared functions once. mise tool shims are prepended after
host-local PATH changes; full activation is lazy on the first `mise` command.
**Tradeoff:** shims select tool versions but do not automatically activate project
environment variables. Set `PROFILE_MISE_MODE=activate` in a host fragment if you
require eager environment hooks (slower). Keep fragments free of redundant
activation calls. Never cache generated environment values.

Hermes overlay selection uses shell builtins; shim verification/repair runs
detached. The prompt renders without a synchronous VCS probe: a single Git pipe
worker updates branch/dirty state through ZLE. Obsolete-directory results are
discarded; branch text is not evaluated as shell code. `compinit` still runs its
security audit, once, with standard completion paths already registered.

`omp` completions load from `${XDG_CACHE_HOME:-$HOME/.cache}/profile/zsh/omp.zsh`.
A disowned worker refreshes missing/stale caches (24 hours, or binary/worker
upgrade). Cold starts pick up the finished cache on a subsequent prompt. A kernel
lock prevents concurrent generators; failures retain the old cache, and successful
writes are syntax-checked and atomically replaced. No generator output reaches the
terminal. Run `bin/zsh/refresh-completions --help` for manual refresh usage.

fzf uses standard package locations or `${FZF_BASE}/shell`, without calling
Homebrew. iTerm integration only loads inside iTerm. Host-local Homebrew setup
should use its known installation prefix rather than launching `brew shellenv`
on every shell startup.

## Tests

- `uv run --no-project tests/test_zsh_sync.py`
- `uv run --no-project tests/test_zsh_startup.py`

Both use isolated fixtures; no host state touched.

## Measurements

- `zsh -df bin/zsh/benchmark-launches`: 3 warmups + 20 launches each for minimal,
  interactive and login shells; NDJSON mean/min/max/standard deviation.
- `zsh -dfi bin/zsh/benchmark-startup`: source-only timings, then first-prompt hooks
  and prompt expansion. No command tracing or environment values are emitted.
- `zsh -dfi bin/zsh/benchmark-startup --modules`: optional module-load timings.

The first measures wall time including process launch; the second excludes it.
Neither includes terminal rendering; validate async prompt updates in a real TTY.
Do not claim sub-100ms wall time from a configuration-only measurement.