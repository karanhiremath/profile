# SOP — behavior `orchestrate`

Applies to any seat whose manifest declares `behavior: [orchestrate]`. The seat
delegates all implementation; it never edits code and never mutates
infrastructure. Validate the manifest first: `aos seat check <manifest.yaml>`.

## Inputs

- Seat manifest (seat.v1): capabilities, tier ladder, buffers, interfaces.
- Job bus (`interfaces.job`) for dispatch and result collection.
- Prefill prompt buffers (`buffers`, via the prompt-buffer primitive).

## Procedure

1. **Check** — run `aos seat check` on the manifest; stop on `ok: false`.
2. **Decompose** — split the request into a delegation graph: nodes are jobs
   with one owner, explicit dependencies, acceptance criteria, and a budget
   (turns/tokens/wall-clock). Keep the graph shallow; prefer sequential
   dependencies over speculative parallel branches.
3. **Route** — enqueue implementation jobs to worker seats over the job bus.
   - pi workers: default rung `together` GLM-5.3-Flash; alternate rungs
     `openai-codex` gpt-5.5 or gpt-6.1-sol.
   - claude CLI workers: sonnet or opus.
   - Launcher flags may select a rung from the ladder; they never redefine it.
   - Match rung to job weight: cheap mechanical edits go low-tier; risky or
     ambiguous work goes high-tier with tighter review.
4. **Prefill** — apply the seat's buffers to each worker prompt before
   dispatch (conventions, guardrails, output contract). Never inline secrets.
5. **Collect and review** — evaluate each result against the job's acceptance
   criteria; run the project's checks. On defects, return a corrective job —
   do not patch the code yourself. A seat with `orchestrate` must not hold
   `code.write`/`infra.mutate` capabilities or write-capable toolsets
   (`file`, `code_execution`); `file_read`-style read toolsets are allowed.
6. **Escalate** — surface to the operator when scope is ambiguous, a job
   fails twice on the same defect, a permission gap appears mid-flight, or a
   budget is exhausted. Report with state/evidence/blockers/next.
7. **Budget context** — on high-tier seats keep context lean: pass paths and
   pointers, not payloads; summarize completed subgraphs before continuing;
   push bulk reading into worker jobs.

## Invariants

- Delegate-only: implementation and infrastructure changes go out as jobs.
- All work flows through the job bus; no side-channel dispatch.
- Worker stdout stays a structured payload; diagnostics go to stderr.
- On any permission prompt the seat cannot grant: halt that job and escalate.