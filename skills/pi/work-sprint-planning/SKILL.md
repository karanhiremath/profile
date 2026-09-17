---
name: work-sprint-planning
description: >-
  Close and pull EOP + KH Linear cycles. Use when the user asks for EOP/MK/KH
  sprint planning, cycle close, a slip table, or Monday/Tuesday cycle planning.
  Read-only packet first. Voice, Headscale, and Hermes runtime are orthogonal.
---

# work-sprint-planning

CoS-W Linear cycle planning. One job: a read-only close/pull packet for EOP and
KH. Not runtime, voice, Headscale, idle-steer `--apply`, or a swarm.

## Scope

**In:** EOP cycle close/pull, KH tracking alignment, o1/o2/o3 lane status, slip
vs close, this-week execution gates.

**Out:** voice / work-phone, Headscale, Hermes tool-loop / Cursor-backend,
host-native runtime repair, Linear writes, `--apply`, swarm spawn.

Spoken **MK** = Linear team **KH** (personal tracking). **MKT** is Marketing
and has no cycles. There is no team key `MK`. If MK was not KH, stop and ask.

## Loop

1. Ground: last ~10 work dailies, case oracles/`MONDAY-PACKET` if present,
   Linear `--team EOP` and `--team KH` with `--cycle active` (and `previous`
   when closing).
2. Keep **o1 / o2 / o3** as parallel lanes. Do not collapse. Do not mix leftover
   KH tooling issues into EOP-o* workspaces.
3. Write a read-only sprint packet: cycle windows, per-lane north star vs live
   vs next, recommended slip vs close, park-until-named-gate, this-week
   execution. No Linear writes, no `--apply`, no swarm.
4. Ask for the slip table (or named exceptions). After approval, inbox-only
   recover via `aop-steer` and `steer-oN.md`. Still no `--apply` until named
   targets.

Done when the packet names every open EOP-active item as pull / park / close
and KH workspaces stay on their own cycle.

## Linear CLI

This workspace has no default team. Always pass `--team EOP` or `--team KH`.
Do not pass `--no-pager`.

If the CLI says `No default team configured`, run `linear team list`, then
retry with `--team`. Same pattern for `linear issue query` / `issue list` /
cycle queries.

EOP (and ENT/BIF/CAR): state transitions only, after approval. Verbose
progress stays on KH.

KH weekly cycles (Mon→Mon) can sit one cycle ahead of EOP. Report both
windows; do not force them to the same number.

## Lanes (do not invent a fourth)

| lane | EOP north star | KH workspace class |
|---|---|---|
| o1 | Nightly FIPS pin vs experimental | KH-329 class |
| o2 | SFDC pentest + Yoshi | KH-330 class |
| o3 | SOC2/HIPAA audit prep | KH-331 class |

Oracles: `eop-project-oracle`, `kh-project-oracle`, repo `*-context`. Verdicts
go to case/drafts. Cos/PM consume. Oracles do not implement.

Team keys, cycle flags, and packet fields:
`references/linear-teams-and-cycles.md`.
