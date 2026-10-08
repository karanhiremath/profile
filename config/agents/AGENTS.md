# Personal Agent Rules — Karan Hiremath

Generic operating rules for coding agents (Claude Code, pi, Codex) on **personal**
machines. No employer/customer/project context — that lives in separate work repos.
Synced read-only from `profile` via `agentic-sync`.

## Isolation / blast radius
- Code changes go in a **git worktree** on a branch, never directly on the default branch.
- Never mount or exfiltrate host credentials: SSH keys, cloud creds, kubeconfigs,
  `auth.json`, browser profiles, 1Password, full `$HOME`.
- Prefer read-only mounts for reference repos. Disposable HOME for containerized agents.
- Confirm before irreversible / outward-facing actions (push, merge, publish, send).

## Secrets
- Never commit secrets or `.env` files. Never print access keys, tokens, or passwords.
- If a secret is needed, reference an env var or a secrets manager — never inline.

## Scripts & tools
- Bash: `set -euo pipefail`, support `--help`. Write durable scripts; don't run
  multi-step work as inline one-liners.
- Every CLI tool ships `<tool> upgrade` (self-update) and bash+zsh completions.
- Human-readable output: real newlines, progress, clean tables — never raw/escaped JSON.
- Research existing OSS before building custom.

## Git
- Commit messages: imperative mood, name the affected component.
- Branch first if on the default branch. Commit/push only when asked.

## Output style
- Treat output as billable bandwidth: terse, no tutorials, no restating tool output.
- Represent uncertainty as fields (`unknown`, `needs-check`, `blocked`, `next`),
  not metacognitive prose ("I realize", "I guess", "it seems like").

## Verification
- Read tool output directly. Don't chain `&& echo "..."` or pipe through `echo`/`printf`
  for status — exit codes and unfiltered stdout speak.
- Test locally before claiming done; report failures with the actual output.

See language conventions in `LANG_*.md` and the execution loop in `AGENTIC_WORKFLOW.md`.
