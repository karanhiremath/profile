---
name: aop-steer
description: Idle-steer / inbox-only fleet nudges. Inventory then proposal; apply only after review.
---

# aop-steer

Inbox-only steer. Follow `idle-steer`. Default is inventory → proposal → oracle
drafts → human review. Never type into a composer.

## Rules

- Never `tmux send-keys` / `herdr pane send-text`.
- Never steer `skip_busy` (includes question UI), `skip_focused`, `skip_dirty_composer`.
- `--apply` needs `--target`. Do not `--all` unless the reviewed proposal says so.
- Cursor sessions stay inbox-only (job-bus). No composer inject.

## Loop

1. Inventory idle panes (stdout proposal). Do not apply.
2. One read-only steer oracle per workstream. Drafts only.
3. Merge into one proposal and wait for review.
4. After approval, apply named targets only.
