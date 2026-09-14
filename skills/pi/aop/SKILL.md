---
name: aop
description: Index for agent operating procedures. Points at attach, handoff, and session-compaction. Does not reimplement them.
---

# aop

Index only. One job per skill — do not add `aop-attach` / `aop-handoff` aliases.

| Need | Skill |
|---|---|
| Open a host/sandbox session (`mac` / `oma` / `*-s`) | `attach` |
| 60/70/75 pointer handoff (`/handoff-bg` → `/handoff-now`) | `handoff` |
| Handoff checklist behind `handoff` | `session-compaction` |
| Herdr split/focus (never a second `herdr server`) | `herdr-pane-management` |
| Cos/CosW host vs `*-s` sandbox | `aos` + `cosw-s <sandbox> [<instance>]` + `attach` |
| AOS REQ gather/align/review | `aos` playbook `aos-requirements-alignment.md` |

Read-only pane inspect: `tmux capture-pane -p`. Never `tmux send-keys` / `herdr pane send-text`.
Detached create on the remote; attach from a real TTY. Do not hang a Hermes terminal on interactive tmux attach.
