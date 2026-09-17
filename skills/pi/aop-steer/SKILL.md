---
name: aop-steer
description: Idle-steer / inbox-only fleet nudges. Inventory then proposal; apply only after review.
---

# aop-steer

Follow `idle-steer`. Default is inventory → proposal → oracle drafts → human review.

```
~/src/karan.hiremath-worktrees/harness-refresh-safe-20260902/scripts/cdev/idle-steer --propose
```

`--apply` needs `--target`. Never `--all` unless the reviewed proposal says so.
Pi apply requires `adapter_status=installed`.
