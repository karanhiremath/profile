---
name: aop
description: Index for agent operating procedures. Points at attach, handoff, session-compaction, and work-sprint-planning. Does not reimplement them.
---

# aop

Index only. One job per skill — do not add `aop-attach` / `aop-handoff` aliases.

| Need | Skill |
|---|---|
| Open a host/sandbox session (`mac` / `oma` / `*-s`) | `attach` |
| 60/70/75 pointer handoff (`/handoff-bg` → `/handoff-now`) | `handoff` |
| Handoff checklist behind `handoff` | `session-compaction` |
| EOP/KH cycle close, slip table, sprint packet | `work-sprint-planning` |
| Herdr split/focus (never a second `herdr server`) | `herdr-pane-management` |

Read-only pane inspect: `tmux capture-pane -p`. Never `tmux send-keys` / `herdr pane send-text`.
Detached create on the remote; attach from a real TTY. Do not hang a Hermes terminal on interactive tmux attach.
