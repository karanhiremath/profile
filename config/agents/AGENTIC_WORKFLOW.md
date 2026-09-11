# Agentic execution workflow (personal)

Default loop for non-trivial work on personal machines.

1. **Orient** — restate the goal in one line; locate the relevant files before editing.
2. **Isolate** — for code changes, create a git worktree on a branch.
3. **Plan** — for 3+ step work, track tasks; keep one in-progress at a time.
4. **Act** — make the change; match surrounding code's idiom, naming, comment density.
5. **Verify** — run it. Read real output/exit codes. Tests + lint where they exist.
6. **Report** — terse summary (1-2 sentences). State what's done, what's unverified.

## Parallelism
- Independent reads/exploration: parallel. Dependent code changes: sequential through review.
- Confirm before push/merge/publish/send unless pre-authorized.

## When stuck
- Don't thrash. Surface a blocker as `blocked: <what> / need: <decision>` and ask.
