# Browser control surfaces

Prefer a native pi browser extension when the user has installed and set it up.
Until then, stay on local, non-CDP fallbacks.

## 1. pi-browser-harness (recommended, not installed here)

Package: `npm:pi-browser-harness`
Docs: https://pi.dev/packages/pi-browser-harness
Repo: https://github.com/amankumarsingh77/pi-browser-harness

```bash
pi install npm:pi-browser-harness
```

Then in Chrome: `chrome://inspect/#remote-debugging` → Discover network
targets → Allow. Or relaunch with `--remote-debugging-port=9222`.

Then in a **native pi TUI** (not this Cursor bridge): `/browser-setup`.
Pin the personal profile with `/browser-profile`. State is
`~/.pi/agent/browser-harness.json`.

Use snapshot refs (`[eN]`), not screenshots, to click. Isolation: the harness
opens its own window and refuses tabs it did not create unless `scope:"all"`
for a read-only list.

Do not install this from a Cursor-bridge session unless the user asked.

## 2. browser-use (absent)

Python CDP agent. Not on PATH, not importable. Do not install unless asked.
If the work Mac already has it, wait for a shared-buffer drop instead of
recreating it here.

## 3. Chrome local fallback (this Mac)

Temporary exception: use signed-in Chrome Default for Perplexity so a new
login is not required. Drive that session with `pi-p` (AppleScript). Do not
CDP-attach that profile.

```bash
open -a "Google Chrome" "https://www.perplexity.ai/library"
~/src/profile/bin/browser-eval/scripts/launch perplexity
```

Cached titles / prompts (prefer the bridge):

```bash
pi-p lookup
pi-p context
../scripts/pplx-threads.py
```

Chrome History SQLite on this host has been empty/schema-less. Prefer
IndexedDB + Sessions strings.

Do not `osascript` Chrome unless Automation is already granted. A previous
tab-list attempt hung.

## 4. Dia

Dia Skills are plain-English shortcuts inside Dia (Skill Builder since Dia
~1.2). They can tell Dia's sidebar what to do with open tabs. They cannot
call pi tools.

When Dia.app exists, paste recipes from `dia-skills.md`. When it does not,
write the recipes only and stop.

An agentic Dia harness was publicly described as a Fall 2026 Browser Company
item. Mark any Dia-side pi RPC as UNVERIFIED unless you can see it in the
installed app.
