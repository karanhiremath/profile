# Generic Hermes project registry examples

This directory is the last-resort, tool-owned registry search path for `pm <project>` and `pl <project>`.

Do not put real work/private project state here. Prefer:

- work-private: `~/src/karan.hiremath/agentic/hermes/projects/<project>.yaml`
- personal-safe: `~/src/hermes/projects/<project>.yaml`

Minimal schema:

```yaml
name: example
aliases: [ex]
description: "One-line project mission."
workdir: /abs/path

pm:
  profile: example-project-manager

tmux:
  pm_session: example-pm
  pl_session: example-pl
  workdir: /abs/path

event_bus:
  ledger: /abs/path/events.jsonl
  publish_paths:
    - path: /abs/path/project-events.jsonl
  sources:
    - key: project-events
      path: /abs/path/project-events.jsonl
      writable: true
  event_types:
    - project_registered
    - pm_started
    - pm_attached
    - project_lead_started
    - project_lead_attached
    - handoff_created
    - pm_action_required
    - task_status
    - kanban_transition
    - blocker
    - decision

handoffs:
  latest_pm: /abs/path/LATEST-pm-handoff.md
  latest_project_lead: /abs/path/LATEST-project-lead-handoff.md
```
