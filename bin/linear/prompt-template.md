---
description: Linear Code & reviews prompt template (personal). Paste into Settings → Code & reviews → Configure coding tools.
---

You are opening this Linear issue in a local `pc` workspace (nvim + pi + zsh).

Issue: {{issue.identifier}}: {{issue.title}}
Suggested branch: {{issue.branchName}}
Project: {{project.name}}

Standing rules:
- Create or check out `{{issue.branchName}}` before edits. Do not invent a different branch name.
- Plan first when the change is cross-cutting; then implement.
- Do not commit secrets, `.env` files, or credentials.
- Prefer existing wrappers over raw cloud / k8s / terraform CLIs for repeated admin patterns.
- KH issues: progress updates are fine. ENT / BIF / CAR: status transitions only.
- Do not run exploit PoCs, packet-level validation, or unauthorized access checks.
- Verification: read tool output directly. Do not chain `&& echo` / `printf` for status.

Start by reading the issue context above, confirming the repo matches the selected workDir, and stating the first concrete step.
