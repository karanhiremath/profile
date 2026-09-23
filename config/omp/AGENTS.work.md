# Work omp

You are running oh-my-pi from the profile-managed work agent dir
(`~/.omp/agent`, selected via `~/.omp/default-profile` / `~/.pi/default-profile`).

Discovery of Claude, Cursor, Codex, Gemini, and other IDE MCP/rules sources
is disabled. MCP is an explicit allowlist only. Do not inherit Datadog or
Cursor plugin servers.

Work project memory lives in `~/src/karan.hiremath`, not in this profile repo.

Linear is P0 via the profile-owned `linear` CLI (official GraphQL API). Auth:
`LINEAR_API_KEY` or `~/.local/share/fleet/linear-token`. Never print the token.
Do not use `@schpet/linear-cli` or npm `@linear/cli` (`lin`). MCP is optional
when a harness actually exposes it.
