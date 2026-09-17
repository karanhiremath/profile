---
name: granola-lookup
description: Explicit Granola meeting lookup for librarian and notetaker profiles only. Use when a loaded librarian/notetaker profile needs a cited meeting, decision, or schedule. Do not use from implementor, reviewer, planner, orchestrator, or context profiles.
disable-model-invocation: true
user-invocable: true
---

# granola-lookup

Meeting MCP is a **notetaker / librarian** capability. Do not load this skill, and do not call Granola, unless the active profile class is `librarian` or `notetaker`.

Implementor sessions stay on job-bus / code / manifests. Work notes live in `~/src/karan.hiremath`. Personal notes live in `~/src/notes`.

## When to run

The user named a meeting, a decision, "what we discussed", who said what, upcoming calls, or asked a PR/commit/doc to cite the meeting that decided it **and** this session is a librarian/notetaker profile.

## Profiles

Load one class profile, then query only that scope:

- [profiles/librarian.yaml](profiles/librarian.yaml) — `work-notes-librarian`
- [profiles/notetaker.yaml](profiles/notetaker.yaml) — `granola-notetaker`

Do not invent workstream Granola folder IDs. Fill folder IDs in those YAML files when known.

## Query

1. Confirm `profile.class` is `librarian` or `notetaker`. If not, stop and say Granola is out of scope for this profile.
2. Use Granola MCP for the cited question only: `query_granola_meetings`, or `list_meetings` for schedule.
3. Answer in four fields: title, date, decision, who.
4. Do not preload `granola-context` / `granola-prep` / `granola-review` / `granola-engineer`.
