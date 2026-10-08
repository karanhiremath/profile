---
name: perplexity-web-research
description: Opt-in Perplexity web research via pplx-research (Search/Agent API). Use only when the user explicitly asks for live web facts, current docs, CVE/compat lookup, or Perplexity-backed research. Do not use for local code, secrets, Cartesia customer data, or routine questions. Default mode is search/ask (fast). Not a primary model and not always-on MCP.
---

# Perplexity web research

Load this skill (`/skill:perplexity-web-research`) or when the user asks for live Perplexity/web research. Call the wrapper only. Do not call `llm`, raw curl, or official MCP from this session.

## Command

```bash
~/src/profile/bin/perplexity/pplx-research \
  --mode search \
  --purpose '<short why>' \
  --query '<question>'
```

`--query-file -` reads stdin. `--out FILE` writes mode-0600 JSON; stdout is still the payload.

| Mode | Backend | Units (cap 20/day UTC) | When |
|---|---|---|---|
| `search` | Search API, low context | 1 | default; ranked URLs/snippets |
| `ask` | Agent `fast` | 2 | short cited answer |
| `reason` | Agent `medium` | 5 | needs `--confirm-expensive` |
| `research` | Agent `high` | 10 | needs `--confirm-expensive` |

`PERPLEXITY_API_KEY` must already be in the environment. Never print it. Never pass Cartesia customer/infra/secret material as the query.

## Budget

Pro/Max is the web/Comet Library. API is a separate meter. Prefer `search`, then `ask`. Do not enable MCP or `/model` Sonar. Cap via `PPLX_DAILY_CAP` / `--daily-cap`.

## Library / Comet chats

Official API cannot list Library threads. Periodic ingest is a separate headed computer-use job, not this CLI.

```bash
~/src/profile/bin/perplexity/pplx-library-sync --check
~/src/profile/bin/perplexity/pplx-library-sync --print-prompt
```

Follow [jobs/library-sync-prompt.md](jobs/library-sync-prompt.md) and [references/library-sync.md](references/library-sync.md). Write only to `~/src/notes/01_in/perplexity-library/`. Skip work/Cartesia threads.
