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

## Tests

`python3 tests/test_zsh_sync.py` (uses `ZSH_SYNC_HOME` fixtures; no host state touched).