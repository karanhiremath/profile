# Pointer handoff — 60 / 70 / 75

In-place `/compact` is fallback only. Auto-handoff is the default on every host.

| % | Action | Command |
|---|---|---|
| ~60 | Prepare sibling in background | `/handoff-bg` or `/snapshot` + sibling spawn |
| ~70 | Align successor prompt | `/handoff` align / compact-handoff align |
| ~75 | Switch | `/handoff-now` |
| overflow | Last resort | `/compact` only if `PI_HANDOFF_PREFER=0` |

## Canonical files (profile → `~/.pi`)

- `config/pi/extensions/handoff.ts` — `/handoff`, `/handoff-bg`, `/handoff-now`
- `config/pi/extensions/compact-handoff.ts` — `session_before_compact` cancel + lane
- `config/pi/extensions/lib/compact-snapshot.ts` — pointer schema + prep
- `config/pi/extensions/lib/handoff-brief.ts` — model-written `/handoff` prompt + stub check
- `config/pi/extensions/lib/handoff-cursor-hook.ts` — Cursor `preCompact` / `stop`
- `skills/pi/session-compaction/SKILL.md` — operator checklist (handoff-first)
- `bin/atop/resolve-skill-conflicts` — one `name:` per Cursor-in-pi catalog; do not fork a second name. Codex `~/.codex/skills/session-compaction` is the stale May 22 compact-first body, not a Cursor adapter.
- `config/cursor/hooks.json` — user-level Cursor hook install (`preCompact`/`stop` → `handoff-lane.mjs`)

Apply: `bin/atop/harness-sync apply` (all host classes).
Pull stack onto a peer: `harness-sync pull --all <host>` then `apply`.

One `handoff.ts` per host. `bin/pi/install` on a work host copies
`~/.pi/work-agent/extensions/*.ts` after `harness-sync apply`, so a `handoff.ts`
left in that overlay replaces this stack and its commands. Delete the overlay
copy or keep it identical to the file here.

## `/handoff` prompt style

| Style | Select | Prompt placed in the new session |
|---|---|---|
| `pointer` (default) | `--pointer` | Snapshot pointer, ≤5% of the window |
| `brief` | `--brief`, `PI_HANDOFF_STYLE=brief`, or `"handoffStyle": "brief"` in `~/.pi/agent/compact-handoff.json` | Prompt written by the current model from the conversation |

The brief applies to interactive `/handoff` only; `/handoff-now`, `/handoff-bg`,
and the lane stay on the pointer. It asks for the headings `Files to read first`
through `Task`, but a complete reply with other headings is kept: you review it
in the editor. Only a stub (empty, under 400 characters, or an unstructured
promise to write the prompt later) is retried once. If that also fails, or the
provider errors, `/handoff` warns and uses the pointer prompt instead of failing.

## Session replacement contract

Capture owner IDs, aliases, paths, and presentation mode before switching.
After `newSession` / `switchSession`, use only the fresh `withSession` context
for UI and message delivery. Persist owner prep through the captured-data writer,
not the replacement session's identity. Cancellation must not mark a switch;
replacement errors must not fall back through a potentially stale owner context.

Offline regression suite (no model, credentials, or live-session replacement):

```bash
node --experimental-vm-modules --test config/pi/extensions/lib/handoff-replacement.test.ts config/pi/extensions/lib/compact-snapshot.test.ts config/pi/extensions/lib/handoff-sibling.test.ts config/pi/extensions/lib/handoff-brief.test.ts
```

After installing extension changes, `/reload` or restart Pi before using them.

## Cursor defect

Cursor host compact does not fire pi `session_before_compact`. Without `~/.cursor/hooks.json` → `preCompact`/`stop`, a Cursor-bridged session dumps in place. The hook must be installed on every host.

## Do not

- Default to `/compact` when `/handoff-now` can continue the work
- Treat a queued `/handoff-now` as a finished switch
- Ask whether to continue after a compact snapshot pull-up
