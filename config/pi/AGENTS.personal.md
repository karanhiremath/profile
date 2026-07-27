# Personal Pi Coding Agent SOP — Karan Hiremath

## Permission Safety — P0

- Never invoke any agent with `--dangerously-skip-permissions`, `--allow-dangerously-skip-permissions`, `--permission-mode bypassPermissions`, `--permission-mode auto`, or equivalent bypass/auto mode.
- Use manual/default permission mode with a task-specific minimum allowlist. Permission gaps must halt for explicit approval; never broaden permissions silently.
- Treat helper scripts, subagents, background jobs, and vendor CLIs as covered by this rule.

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

## Output & Thinking Formatting Policy — P0

Applies to every model and agent in this profile. Optimize for machine- and human-grokability; minimize token cost and mental work.

### Response body — default to structured output

Prefer, in order of fit (pick the lightest representation that fits; do not stack all):

1. **Tables** — comparisons, status, inventories, key/value sets, gate results.
2. **YAML / JSON code blocks** — config, state, manifests, data shapes. Always fenced, always valid (no trailing commas; no comments in JSON). Use YAML for humans, JSON for machines.
3. **Mermaid diagrams** — flows, sequences, call chains, dependency graphs, decision trees, state machines. Use `graph TD` / `flowchart` / `sequenceDiagram` / `stateDiagram-v2` as fit.
4. **Shell / code code blocks** — proposed commands or code samples. Copy-pasteable; shell uses `set -euo pipefail`.
5. **ASCII / mermaid charts** — only when a table or diagram does not fit.

### Response body — text discipline

- **No prose paragraph > 3 lines.** If a paragraph grows, refactor into bullets, a table, or a diagram.
- **One idea per block.** Label each block with a leading `**label**:` or a short heading.
- **Facts vs inference vs unknown.** Mark inferences with `→`, unknowns with `unknown` / `needs-check`. Never mix inference into a fact table without a column.
- **Status reports** — use the established status-block format (YAML or the project's status template). Never free-text a status update.
- **Code changes** — always show the proposed diff/snippet as a fenced code block before or instead of describing it in prose.
- **No emoji** unless the user asks. **No preamble** — don't narrate tool calls or restate the request; output the result.
- **Don't over-decorate** — a one-line factual answer needs no table/diagram; don't add a mermaid that restates a 2-row table.

### Thinking blocks

- **Plan before acting**, in the thinking block, not in the visible response.
- **Structure thinking** as: `goal → options → pick → steps → risks`. Bullets or numbered, not prose.
- **Keep thinking terse and load-bearing.** No restating the prompt, no meta-commentary, no narrating obvious steps.
- **Surface uncertainty in thinking** (`unknown`, `needs-check`) and resolve it before committing to an action in the response.
- **Never leak thinking-block content** into the visible response unless the user asks for the reasoning.

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
