---
description: Work a Linear issue in the current pc workspace
argument-hint: "<ISSUE-ID> [branch]"
---

Work Linear issue ${1:-the issue in the current brief}.

Suggested branch: ${2:-the issue's Linear branch name}

Standing rules:
- Create or check out the suggested branch before edits.
- Plan first when the change is cross-cutting; then implement.
- Do not commit secrets, `.env` files, or credentials.
- Prefer existing wrappers over raw cloud / k8s / terraform CLIs for repeated admin patterns.
- KH issues: progress updates are fine. ENT / BIF / CAR: status transitions only.
- Do not run exploit PoCs, packet-level validation, or unauthorized access checks.
- Verification: read tool output directly. Do not chain `&& echo` / `printf` for status.

If a brief exists at `$HOME/.cache/linear/open-issue/${1:-$LINEAR_ISSUE_IDENTIFIER}.md`, read and execute it. Otherwise pull the issue with `linear issue view` / MCP and start.
