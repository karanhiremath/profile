---
name: dia-browser
description: "Build Dia Skills and drive a signed-in Chromium browser from pi. Use when the user mentions Dia, Dia Skills, browser-use, pi-browser-harness, Perplexity library recovery, or controlling Chrome/Dia from a coding agent."
disable-model-invocation: true
user-invocable: true
argument-hint: "preflight|dia-skills|pplx-threads|chrome-open [url]"
---

# Dia + pi browser control

Recovered Perplexity prompt (Chrome IndexedDB; best UUID
`c2ecf226-bb4b-4263-a1c1-690557005713`, also seen on
`6678499c-7e60-45b1-aed7-ed1b060e27ea`):

```text
building out skills in dia so pi coding agent can be used to control the browser. also can we figure the best remote management app for [mac] (securely use existing pi sessions e.g. ...)
```

The answer body is not in local cache. Do not invent missing Dia APIs.
Treat Dia Skills as natural-language shortcuts in Dia. They do not grant pi tools.

## This host (verify, don't assume)

| Surface | Status on the personal Mac |
|---------|----------------------------|
| Dia.app | eval-only at `~/.local/share/browser-eval/apps/Dia.app` |
| Google Chrome | present, logged into Perplexity |
| `browser-use` / `browser_use` | absent |
| `pi-browser-harness` | not in `~/.pi/agent/settings.json` |
| `browser-eval` | `~/src/profile/bin/browser-eval` |
| Shared buffer `~/.pi/agent/buffers` | INDEX stale unless `sync.log` shows a new commit |

Work-machine installs do not appear here. Do not `pip install browser-use` or
`pi install npm:pi-browser-harness` unless the user asks. Both attach to a
real signed-in browser.

## Preflight

```bash
"$SKILL_DIR/scripts/preflight.sh"
```

`$SKILL_DIR` is this skill directory (parent of `SKILL.md`).

## What to do

1. Run preflight. Report Dia / Chrome / harness / buffer facts.
2. If the user wants Dia Skills, write or update the plain-English recipes in
   [references/dia-skills.md](references/dia-skills.md). Paste them into Dia's
   Skill Builder when Dia exists. Do not claim they are installed here.
3. If the user wants pi to drive Chrome **now**, use signed-in Chrome Default
   for Perplexity only (no new profile / no CDP) via
   [references/surfaces.md](references/surfaces.md) and `pi-p`:
   - `pi-p tabs` / `focus` / `new` (AppleScript URLs; no JS needed)
   - `pi-p read` / `steer` / `md` after View → Developer → Allow JavaScript from Apple Events
   - `pi-p search` routes to the official API when keyed, else a new tab
   - IndexedDB catalog via `pi-p lookup`. Do not CDP-attach Chrome Default.
4. To recover a Perplexity prompt:

```bash
"$SKILL_DIR/scripts/pplx-threads.py"
open -a "Google Chrome" "https://www.perplexity.ai/library"
```

5. Recommended next install (ask first): `pi install npm:pi-browser-harness`,
   then Chrome remote debugging + `/browser-setup` in a native pi TUI. That is
   the real control plane. `browser-use` is the older Python twin; do not add
   both.

## Rules

- Personal host: no work credentials, no work vault, no silent CDP attach.
- Do not type Perplexity / Google passwords. Stop at an auth wall.
- Do not dump full IndexedDB blobs or cookies into notes.
- Do not start `herdr server` from inside a Herdr/Pi pane.
- Shared-buffer drops land in `~/.pi/agent/buffers` and
  `~/src/notes-pi-buffers/pi-buffers`. Watch `buffers/sync.log`. Do not invent
  a drop that is not there.

## Known recovered threads (local Chrome cache)

| UUID | Title (as cached) |
|------|-------------------|
| `c2ecf226-bb4b-4263-a1c1-690557005713` | building out skills in dia so pi coding agent can be used to control the browser. also can we figure |
| `d7185ad3-c551-4f99-b386-bdd4cf3d97f2` | Analyze the days most significant technology developments… |
| `afa08a34-56d0-4ab3-ba46-26d8c80ffcae` | Find the top trending Chinese-language technical posts… |
| `528b21c8-402e-4837-8841-2b91ca4223be` | best terminal gh pr review + linear review agent toolkit |
| `34e755c3-f80d-431e-8584-59e5903fa55b` | multi-harness mnemosyne - how can it be best implemented??? |

Open a thread with:

```text
https://www.perplexity.ai/search/<uuid>
```

Skill directory: this file's parent.
