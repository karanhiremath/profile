# Linear teams and cycle queries

Session-derived map for CoS-W sprint planning. Query flags, not a live board.

## Team keys

| spoken / shorthand | Linear key | role |
|---|---|---|
| EOP | `EOP` | Enterprise, On-Prem, Partnerships — cycle-bearing work |
| MK / KH | `KH` | Karan personal tracking — verbose progress |
| MKT | `MKT` | Marketing — not sprint planning, no cycles |
| ENT / BIF / CAR | those keys | team-visible; state transitions only |

There is no Linear team `MK`. Default spoken MK → KH unless the user names a
person or `MKT`.

KH team id (when an API needs uuid): `239e44b6-e11e-46d2-81f9-309959987e1b`.

## CLI contract

No default team is configured. Always:

```bash
linear team list
linear issue list --team EOP --cycle active
linear issue list --team KH --cycle active
```

Use `--cycle previous` when closing. Do not pass `--no-pager` (not a flag).

Prefer `@schpet/linear-cli` / `linear` before custom GraphQL. Linear MCP is
fine when configured. Shared fleet token at `~/.local/share/fleet/linear-token`
is last resort for grounding. KH overview/documents/loops writes go through
`~/src/karan.hiremath/scripts/linear/steward.sh` and
`~/.local/share/fleet/linear-token-steward` (never the shared key). Grounding
in this skill is read-only.

## Cycle offset

KH is weekly Mon→Mon. EOP cycles can close on a different weekday (recently
Tue). KH may already be on N+1 while EOP is still on N. Report both. Do not
move EOP issues until the slip table is approved.

## Sprint packet fields

```text
eop-cycle / kh-cycle / windows
parallel: o1 / o2 / o3 (do not collapse)
per lane: EOP north star · KH workspace · live · next
slip vs close table
park / named-gate table
this-week execution (still three lanes)
never: Linear/GH publish · --apply · swarm · voice/Headscale
```

Write the packet under the active case when one exists (example:
`~/src/karan.hiremath/.csec/cases/<case>/EOP-SPRINT-<YYYYMMDD>.md`).
