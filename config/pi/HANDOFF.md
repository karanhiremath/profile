# Pointer handoff — 60 / 70 / 75

In-place `/compact` is fallback only. Auto-handoff is the default on every host.

| % | Action | Command |
|---|---|---|
| ~60 | Prepare sibling in background | `/handoff-bg` or `/snapshot` + sibling spawn |
| ~70 | Align successor prompt | `/handoff-align` |
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

Apply handoff only: `bin/atop/harness-sync apply-handoff` (all host classes; leaves settings, auth, and running sessions untouched).
Full harness apply: `bin/atop/harness-sync apply`.
Pull stack onto a peer: `harness-sync pull --all <host>` then `apply`.

## Session replacement contract

Capture owner IDs, aliases, paths, and presentation mode before switching.
After `newSession` / `switchSession`, use only the fresh `withSession` context
for UI and message delivery. Persist owner prep through the captured-data writer,
not the replacement session's identity. Cancellation must not mark a switch;
replacement errors must not fall back through a potentially stale owner context.

`/handoff` and `/handoff-now` automatically submit a continuation in every mode.
`/handoff-bg`, prepare, and align never open dialogs. Editor text is never delivery.
A competing prepare gets at most five seconds of grace; missing child/job references
with expired claims do not block forever. Event-path command dispatch does not also
launch a competing successor worker. Safety vetoes/errors remain explicit; no approval
or permission guard is bypassed.

## Complete state, small pointers

The snapshot is a bounded preview, not the authoritative full task. `state_path`
points to a `pi.handoff-state.v1` manifest for complete **selected** continuation fields:
objective, last three real user requests, last assistant text, extracted next/blockers,
files, jobs, and PRs. This is not a transcript dump and does not include tool outputs.

- Manifest: `data_path`, per-field `first_line`, `lines`, UTF-8 `bytes`, SHA-256.
- Data: NDJSON records `{field, offset, text}` with at most 1,000 characters per chunk.
- Read relevant field pages with `read(offset=first_line, limit=...)`. Concatenate the
  records' `text` in offset order, then JSON-decode the complete field.
- Fields omitted from the preview remain recoverable; pointers omit optional whole
  lines rather than slicing paths or the execution instruction. No `[truncated]` placeholder.
- State files are mode 600. Pre-existing summaries/truncation cannot be reconstructed.
- Child snapshots inherit complete prior state when their only request is a handoff pointer.

Offline regression suite (no model, credentials, or live-session replacement):

```bash
node --experimental-vm-modules --test config/pi/extensions/lib/handoff-replacement.test.ts config/pi/extensions/lib/compact-snapshot.test.ts config/pi/extensions/lib/handoff-sibling.test.ts config/pi/extensions/lib/handoff-state.test.ts
bash tests/test_handoff_install.sh
```

Running processes retain their loaded extension code until `/reload` or restart.
Installation does not dismiss an already-open old dialog or mutate a live session.

## Cursor defect

Cursor host compact does not fire pi `session_before_compact`. Without `~/.cursor/hooks.json` → `preCompact`/`stop`, a Cursor-bridged session dumps in place. The hook must be installed on every host.

## Do not

- Default to `/compact` when `/handoff-now` can continue the work
- Treat a queued `/handoff-now` as a finished switch
- Ask whether to continue after a compact snapshot pull-up
