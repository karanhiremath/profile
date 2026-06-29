# Devin CLI Security Policy — profile

Operator-facing security boundary for Devin CLI in this repo.

## Threat model

| Threat | Mitigation |
|---|---|
| Secret exfil via reads (`~/.ssh`, `~/.aws/credentials`, `~/.pi/agent/auth.json`, `~/.claude/.credentials*`, `~/.Codex/auth.json`, `~/.local/share/fleet/`) | `deny` Read on all of the above in `.devin/config.json` |
| Secret commit via writes to `.env*` | `deny` Write on `**/.env*` |
| Git internals tampering | `deny` Write on `**/.git/**` |
| Destructive shell ops (`sudo`, `rm -rf`, `git push --force`, `git reset --hard`) | `deny` Exec on each |
| Unattended brew/curl/installer execution | `ask` Exec on `brew`, `curl`, `./install.sh`, `./bin` |
| Read of unrelated home-dir secrets | Devin defaults: read-only ops auto-approved only inside CWD; absolute-path reads outside still prompt (allowlist scopes use `~/.ssh` etc. as explicit denies) |

## Allowlist rationale

Auto-approved Execs are read-only or local-only:
`just`, `ls`, `pwd`, `which`, `rg`, `git status|diff|log|branch|fetch|show|add|commit`, `gh pr list|view`, `gh issue list`.

No `git push` in allow — pushing always prompts.

## What is NOT covered here

- Org-level enforcement (set via Devin Team Settings, not project config)
- Sandbox (`--sandbox`) — upstream-marked unstable; use only when explicitly invoked
- MCP server permissions — inherited from `~/.config/devin/config.json` and `~/.claude/`

## Related

- Global rules: `~/AGENTS.md`, `~/.claude/CLAUDE.md`
- Global Devin config: `~/.config/devin/config.json`, `~/.config/devin/AGENTS.md`
- Cartesia security wrappers (when used cross-repo): `cauth`, `caudit`, `cscan`, `cpatch`, `cdev`
