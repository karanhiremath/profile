# Job: ingest new Perplexity Library threads (personal only)

Read-only against Perplexity. Write only under `~/src/notes/01_in/perplexity-library/` and `~/.local/share/pplx-research/library-sync-state.json`.

## Auth

Use headed computer-use / `browser-use` with `user_data_dir=~/.config/cuse/profile/` (`headless: false`). If SSO/MFA appears, stop and let the operator finish login. Do not export cookies. Do not read `PERPLEXITY_API_KEY`. Do not call `https://api.perplexity.ai`.

## Steps

1. Read state: `~/.local/share/pplx-research/library-sync-state.json` (create via `pplx-library-sync --check` if missing).
2. Open `https://www.perplexity.ai/library`. Inventory thread titles + relative dates. Do not dump the full DOM into notes.
3. Skip any thread that looks work/Cartesia-related (customer names, infra, security findings, Linear, internal Slack, NDA). Generic personal tech research is OK.
4. For each unseen personal thread (cap 8 per run): open it, extract title, date, user questions, assistant answers, citation URLs.
5. Write one markdown note per thread:

```markdown
---
tags:
  - notes/inbox
  - perplexity/library
source: perplexity-library
synced: <UTC date>
---
# <title>

- url: <library url if visible>
- date: <thread date>

## Exchange

### User
...

### Perplexity
...

## Citations
- <url>
```

Filename: `YYYY-MM-DD-<slug>.md` under `~/src/notes/01_in/perplexity-library/`.
6. Update state: append seen titles, set `last_run` UTC. Mode 0600.
7. Stop after the cap or when remaining threads look work-related. Summarize counts on stderr only.

## Do not

- Mutate Perplexity (delete, share, rename)
- Commit `notes` unless the operator asks
- Copy cuse profile between machines
- Put secrets, API keys, or cookie values in notes
