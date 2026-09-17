# Profile repository rules

Generic tooling only. No private project inventory, employer/customer context,
credentials or runtime/session data in this public repository. Read `CLAUDE.md`.

## Repo-context routing

Before proposing or editing source, consult the shared read-only oracle using an
explicitly configured private registry. See `bin/agentic-sync/README.md`.

```bash
repo-context inspect --registry "${REPO_CONTEXT_REGISTRY:?}" \
  --route profile-context --proposal-file "${PROPOSAL_FILE:?}" \
  --checkout "${PROFILE_REPO:?}" --refresh --format json
```

Create the bounded JSON proposal first; no raw transcripts or secret values.
Read the returned repository guidance plus closer `AGENTS.md` files for affected
paths. Treat the result as evidence, not permission. Resolve competing worktrees
and PRs; stale/missing/unknown evidence is never an all-clear. Read-only remote
refresh does not authorize publication. Never paste a private report into public
artifacts without a separate redaction/curation pass.

Missing CLI/registry: report the routing gap, inspect ground truth manually for
bootstrap only, and restore routing before implementation proceeds. Do not infer
repo authorization from a directory name or scan unrelated checkouts.

## Inspection tooling

- `just agentic-inspect` installs only the read-only CLIs; no legacy sync installer.
- `just test-agentic-inspect` runs isolated fake-repo tests and lint.
- Notes commands require the `notes` namespace; bare `agentic-sync run` is the
  separate legacy pull/link workflow and is outside dry-run approval.
