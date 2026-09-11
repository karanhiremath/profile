# Work omp

You are running oh-my-pi from the profile-managed work agent dir
(`~/.omp/agent`, selected via `~/.omp/default-profile` / `~/.pi/default-profile`).

Discovery of Claude, Cursor, Codex, Gemini, and other IDE MCP/rules sources
is disabled. MCP is an explicit allowlist only. Do not inherit Datadog or
Cursor plugin servers.

Work project memory lives in `~/src/karan.hiremath`, not in this profile repo.
