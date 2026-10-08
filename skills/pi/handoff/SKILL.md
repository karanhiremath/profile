---
name: handoff
description: "Pointer-snapshot session handoff. Use when the user types /handoff or /skill:handoff, context is 60-75%, or work must continue in a successor session. Prefer /handoff-bg then /handoff-now over /compact."
user-invocable: true
argument-hint: "[--type implementation|monitoring|planning] [--budget 5] [goal]"
---

# /handoff

This is the operator-facing handoff skill. The extension commands are the runtime. Do not dump transcripts. Do not default to `/compact`.

## If the user invoked this skill

1. Infer goal from `$ARGUMENTS` or the current session objective.
2. Run the extension, do not reimplement it:
   - no switch yet → `/handoff-prepare --type <kind> --budget 5 <goal>`
   - user asked to switch / context ~75% → `/handoff-now --type <kind> --budget 5 <goal>`
   - user asked for a reviewable prompt in TUI → `/handoff --type <kind> --budget 5 <goal>`
3. Report snapshot + sibling/prep paths. A queued `/handoff-now` is not a finished switch.

## Lane

| % | Action | Command |
|---|---|---|
| ~60 | prepare sibling | `/handoff-bg` or `/handoff-prepare` |
| ~70 | align successor | `/handoff-align` |
| ~75 | switch | `/handoff-now` |
| overflow | last resort | `/compact` only if `PI_HANDOFF_PREFER=0` |

Cursor host compact does not fire pi `session_before_compact`. Need `~/.cursor/hooks.json` `preCompact`/`stop` → `handoff-lane.mjs`.

## Checklist (keep short)

```yaml
state: active | paused | blocked | ready-for-review
objective: <one line>
snapshot: ~/.pi/agent/snapshots/<sid>.json
prep: ~/.pi/agent/handoffs/<sid>.json
next:
  - <next action>
```

Detailed retro/checklist: `session-compaction` skill.

$ARGUMENTS
