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
- CLI stdout is structured JSON/NDJSON/YAML only; human diagnostics go to stderr.
  Side-channel events must be redacted and must not contaminate stdout.
- Research existing OSS before building custom.

## Repo-context routing
- Before source changes, use `repo-context inspect` with the private registry from
  `REPO_CONTEXT_REGISTRY`, an exact repo/route, a bounded JSON proposal and an
  explicit checkout root. `--refresh` reads GitHub metadata; it never fetches/pulls.
- Read returned guidance and closer repo instructions, then resolve placement and
  competing branches/PRs. Missing evidence is not an all-clear; oracle output is
  never approval to mutate, publish or grant permissions.
- The shared registry is the route inventory across harnesses. Do not duplicate
  private repo lists in public tooling or overwrite existing specialist agents.
- Missing CLI/registry: surface the bootstrap gap; no silent bypass. Generic
  installation and schema: `bin/agentic-sync/README.md` in the tooling checkout.

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
