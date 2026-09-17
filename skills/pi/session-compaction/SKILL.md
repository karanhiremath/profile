---
name: session-compaction
description: "Prepare early session handoffs at 60-75% context utilization. Handoff-first: background sibling at ~60%, align at ~70%, switch at ~75%. In-place /compact is fallback only."
---

# Session Handoff (handoff-first)

Use this skill when context utilization reaches **60-75%** or when a workstream will continue across sessions.

Do not wait for the hard context limit. Do not default to `/compact`. Prepare a background handoff at ~60% and switch at ~75%.

## Trigger

Start the handoff lane when any of these is true:

- context utilization is approximately `60-75%`
- several workstreams/files have been touched
- external state was created: branch, worktree, PR, case, cloud job, shared-drive artifact
- the next task depends on remembering decisions from this session
- the user says to pause, resume later, or wait for an external response

## Lane

| % | Action | Do |
|---|---|---|
| ~60 | prepare | `/handoff-bg` or `/snapshot --type <kind> --budget 5`. Write prep + continuation. Spawn successor wait=false. Do not wait for a human to start it. |
| ~70 | align | Keep successor prompt current. Do not dump transcripts. |
| ~75 | switch | `/handoff-now`. A queued command is not a finished switch. |
| overflow | fallback | `/compact` only if `preferHandoff` is off (`PI_HANDOFF_PREFER=0`). |

Cursor host compact does not fire pi `session_before_compact`. Cursor sessions need `~/.cursor/hooks.json` `preCompact`/`stop` → `handoff-cursor-hook`.

## Helpers

If the harness supports subagents, delegate a read-only pass. In pi, prefer `codex-cli-helper` for high-token retros.

```text
Summarize this session for continuation. Preserve facts, decisions, paths, branches, validation results, blockers, and exact next steps. Omit narrative and internal reasoning. Flag any uncommitted/unpushed work and any external-share gates that must be rerun.
```

Also delegate a read-only retro when the session had rework, user-preference corrections, validation failures, multi-repo changes, or a compact-instead-of-handoff event.

## Retro checklist

```yaml
scorecard:
  context_management: {score: 1-5, evidence: [], improvement: []}
  user_preference_adherence: {score: 1-5, evidence: [], improvement: []}
  tool_efficiency: {score: 1-5, evidence: [], improvement: []}
  validation_rigor: {score: 1-5, evidence: [], improvement: []}
  security_persistence: {score: 1-5, evidence: [], improvement: []}
metrics:
  files_created: <number-or-unknown>
  files_modified: <number-or-unknown>
  validation_commands: <number-or-unknown>
  rework_events: <number-or-unknown>
what_went_wrong_or_nearly_wrong: []
forward_changes:
  policy_updates: []
  skill_updates: []
  instrumentation: []
  delegation_triggers: []
```

## Handoff checklist

```yaml
state: active | paused | blocked | ready-for-review
objective: <one line>
current_decision: <what was decided>
shareable_artifacts: []
internal_only_artifacts: []
paths:
  repo: <path>
  worktree: <path>
  branch: <branch>
  case: <case-path-if-any>
  snapshot: <~/.pi/agent/snapshots/...>
  prep: <~/.pi/agent/handoffs/...>
  continuation_prompt: <path-if-created>
external_state:
  prs: []
  issues: []
  builds: []
  shared_drive_paths: []
validation:
  commands_run: []
  results: []
blockers: []
next:
  - <next action>
owner: <human/team/agent>
```

## Continuation prompt

Create a continuation prompt when work depends on external response or future delivery.

Must include: files to read first, current state, do-not-share list, share/validation gates, worktree/branch status, task classification, terse output style.

## Do not include

- secrets or auth material
- local absolute paths in customer-facing artifacts
- speculative reasoning presented as fact
- stale TODOs without owner/next action

## Final response after handoff prep

```text
state: handoff-ready
persisted:
- <snapshot path>
- <prep path>
- <continuation prompt path>
next: /handoff-now at ~75% or resume from <prompt path>
```
