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
- `config/pi/extensions/lib/handoff-cursor-hook.ts` — Cursor `preCompact` / `stop`
- `skills/pi/session-compaction/SKILL.md` — operator checklist (handoff-first)
- `bin/atop/resolve-skill-conflicts` — one `name:` per Cursor-in-pi catalog; do not fork a second name. Codex `~/.codex/skills/session-compaction` is the stale May 22 compact-first body, not a Cursor adapter.
- `config/cursor/hooks.json` — user-level Cursor hook install (`preCompact`/`stop` → `handoff-lane.mjs`)

Apply: `bin/atop/harness-sync apply` (all host classes).
Pull stack onto a peer: `harness-sync pull --all <host>` then `apply`.

## Cursor defect

Cursor host compact does not fire pi `session_before_compact`. Without `~/.cursor/hooks.json` → `preCompact`/`stop`, a Cursor-bridged session dumps in place. The hook must be installed on every host.

## Do not

- Default to `/compact` when `/handoff-now` can continue the work
- Treat a queued `/handoff-now` as a finished switch
- Ask whether to continue after a compact snapshot pull-up
