# Personal Pi Coding Agent SOP — Karan Hiremath

## Scope Boundary

- Personal work only.
- Allowed project repos: GitHub repositories owned by `karanhiremath/*`.
- Before modifying any repo, verify `git remote get-url origin` resolves to GitHub owner `karanhiremath`.
- Do not read, summarize, copy, or modify Cartesia/work-private repos, notes, credentials, or infrastructure.
- Never use `~/src/karan.hiremath`, Cartesia Linear/Slack/internal docs, work kubeconfigs, cloud projects, or work security findings as context.
- If a request needs work-private data, stop and ask to use the work machine/work chief-of-staff instead.

## Default Work Style

- Terse ops style: bullets, tables, YAML/JSON, checklists, commands.
- Separate facts from inference; mark unknowns as `unknown` / `needs-check`.
- Prefer durable, repeatable repo-local scripts over one-off multi-step shell snippets.
- Never print secrets, tokens, cookies, SSH private keys, or auth material.
- Do not commit `.env`, secrets, local inventories, or machine-specific credentials.

## Personal Repo Conventions

- `~/src/profile`: personal tooling/dotfiles only; no Cartesia data.
- `~/src/hermes`: personal Hermes profiles/workflows; no Cartesia data.
- `~/src/notes`: personal notes; work references must be sanitized to generic load/category only.
- Prefer git worktrees for agent-driven changes.
- Before handoff, run `git status --short --branch` and report uncommitted work.

## Language / Tooling Defaults

- Python: use `uv` / `uv tool`; do not use bare `pip` for project setup unless an existing installer requires it.
- Go: build binaries with `go build -o bin/<name>`; keep `go.sum` current.
- TypeScript/Node: use the package manager already present in the repo; prefer `pnpm` for monorepos.
- Shell scripts: `set -euo pipefail`, support `--help`, keep commands copy-pasteable.

## Safety Rails

- Do not kill/cancel long-running installs/builds/scans unless explicitly asked or there is a clear secret/safety risk.
- For auth/credential changes: present a plan first, then proceed only after approval.
- For host mutation: prefer existing profile recipes/Ansible; avoid ad-hoc raw admin commands.
- For new personal automation: keep it personal-safe and GitHub-syncable in `karanhiremath/*` repos.

## Mini Host Notes

- `cos` launches the personal Chief-of-Staff Hermes profile.
- `agents`, `pm`, `pl`, `herm`, `hermes`, and `pi` should resolve from `~/.local/bin` or `~/src/profile/bin/*` aliases.
- Use `tmux` sessions for long-running installs and agent work.
