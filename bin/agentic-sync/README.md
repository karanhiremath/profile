# Read-only notes planning and repository context

This package extends the existing `agentic-sync` namespace. **Phase one only:**
no notes publication, inbound pull, scheduler, profile activation or credential
repair. Bare `agentic-sync run` is the separate legacy pull/link implementation;
do not use it as a notes command.

## Install / upgrade / test

```bash
just agentic-inspect
just test-agentic-inspect
# Equivalent explicit upgrade; never runs the legacy installer:
./bin/agentic-sync/install-inspect --upgrade
```

Requires Git, `uv` and Python 3.12+. Runtime dependencies: standard library only.
`gh` is required only for explicit oracle `--refresh`.
Installer creates the `agentic-sync-notes` and `repo-context` CLI entrypoints via
`uv tool install --editable`; retain the source checkout while installed. It does
not replace agent definitions, source host config, link profiles or install cron.
Do not run `bin/agentic-sync/install` for this phase: that is the legacy installer.

`agentic-sync` itself remains the existing shell wrapper. Use its explicit path
when it is not on PATH. `agentic-sync-notes` is its equivalent installed notes
entrypoint. Both inspection CLIs support JSON `--help`.
Bash completions: source `completions/inspection.bash`. Zsh: add `completions/`
to `fpath` before `compinit`. Shell startup files are never edited automatically.

## Notes policy and commands

Save a host-selected policy file, outside public artifacts when it contains
private repository metadata:

```json
{
  "schema_version": 1,
  "scope": "personal",
  "repo": "example/notes",
  "checkout_env": "PERSONAL_NOTES_ROOT",
  "target_branch": null,
  "allowed_roots": ["03_tech/agentic-os/projects"]
}
```

`target_branch: null` means unselected, not default branch. `allowed_roots` selects
**inspection candidates only**, not approval to publish. Empty roots are allowed
and report a configuration blocker. No environment-variable interpolation or
shell sourcing is performed on JSON; `checkout_env` names one required variable.
An explicit `--checkout <absolute-root>` overrides that variable.

```bash
./bin/agentic-sync/agentic-sync notes status --config "${NOTES_POLICY:?}" \
  --checkout "${PERSONAL_NOTES_ROOT:?}" --format json
./bin/agentic-sync/agentic-sync notes plan --config "${NOTES_POLICY:?}" \
  --checkout "${PERSONAL_NOTES_ROOT:?}" --format json
./bin/agentic-sync/agentic-sync notes run --dry-run --config "${NOTES_POLICY:?}" \
  --checkout "${PERSONAL_NOTES_ROOT:?}" --format json
# Structured stdin:
agentic-sync-notes plan --config - --checkout "${PERSONAL_NOTES_ROOT:?}" < "${NOTES_POLICY:?}"
```

`AGENTIC_SYNC_NOTES_CONFIG` can select the policy when `--config` is absent.
`--publish` and `run` without `--dry-run` are unconditionally rejected, even with
an otherwise valid policy. No write implementation is hidden behind these flags.

Plans expose relative candidate paths/status, omission counts and blockers. They
never read note bodies or claim content/secret/work-boundary validation. Git itself
may compare file content for status; external filters and fsmonitor are disabled.
Symlinks, non-regular files, nested repos, renames, deletions and unsupported file
types cannot become approved candidates. Secret/runtime-looking paths are omitted
without echoing their names. This filter is not a complete secret detector.
Feature branches and unresolved baselines are flagged; pre-existing staged changes
are preserved. Delivery checkpoint fields are `null`/`not_implemented`, never a
fabricated successful sync timestamp. Concurrent file edits preserving Git status
are not detectable by this metadata-only phase; no snapshot consistency is claimed.

## One private registry, many routes

```json
{
  "schema_version": 1,
  "repositories": [{
    "repo": "example/notes",
    "visibility": "private",
    "owner_project": "graph-engineering",
    "checkout_env": "PERSONAL_NOTES_ROOT",
    "canonical_paths": ["03_tech", "01_in"],
    "guidance": ["CLAUDE.md"],
    "routes": ["notes-context"]
  }]
}
```

All keys are required; unknown/duplicate keys, repos and aliases are rejected.
Empty canonical/guidance arrays represent incomplete placement inventory, not
permission to put files anywhere. Never duplicate the private registry into public
config or derive authorization by crawling a host's source directory.

Proposal payload:

```json
{
  "schema_version": 1,
  "repo": "example/notes",
  "paths": ["03_tech/new-project.md"],
  "intent": "Check canonical placement and overlapping work."
}
```

No raw transcript, note body or credentials in proposals. Intent is not executed,
interpreted as authority or echoed into output. A caller/model reads the returned
guidance and affected sources for semantic analysis; this CLI supplies evidence,
not an LLM all-clear.

```bash
repo-context routes --registry "${REPO_CONTEXT_REGISTRY:?}" --format json
repo-context inspect --registry "${REPO_CONTEXT_REGISTRY:?}" \
  --route notes-context --proposal-file "${PROPOSAL_FILE:?}" \
  --checkout "${PERSONAL_NOTES_ROOT:?}" --refresh --format json
```

`--repo <owner/name>` can replace `--route`; both resolve the same registry entry.
Registry or proposal can use `-` for stdin, but not both. `REPO_CONTEXT_REGISTRY`
is also the default when `--registry` is absent.

- Exact checkout root and origin fetch/push identities must match the registry.
  Only standard GitHub HTTPS and `git@github.com:` URLs are accepted; URLs with
  credentials, other hosts, local remotes and subdirectories fail closed.
- Current and sibling dirty paths, local branch diffs and open PR file overlaps
  are reported. Prunable/missing siblings and bounded/truncated inventory remain
  explicit missing evidence. Broad historical branch overlaps are conservative
  candidates for review, not proof of active competing work.
- `--refresh` uses read-only GitHub repo/PR metadata calls; no fetch/ref updates,
  checkout, GitHub writes or auth repair. Without it, remote evidence is unknown.
  Failed remote queries never expose their raw diagnostics. PR inventories at
  conservative pagination limits are partial, never silently complete.
- The default report is **private**, even for a public repository: dirty branches
  may contain private draft metadata. `--audience public` rejects private repos
  and withholds all local evidence for public repos. Never publish a full private
  report without a separate curation pass.
- `overlap`, `unknown`, `needs-decision` are evidence states, never authority to
  mutate. Phase one never emits a semantic `ready`. Read `guidance_to_read`, then
  closer repo instructions, and reconcile peers before implementation.

Generic routing instructions live in root `AGENTS.md` and
`config/agents/AGENTS.md`. They are source changes, not proof every active harness
has reloaded them. Existing specialized context agents are not overwritten.

## Output and event contract

One JSON object on stdout (including help/rejections). Human diagnostics only on
stderr. Exit 0 means inspection completed, **not** publication is safe; inspect
`state`/`blockers`. Exit 2 means invalid input, identity, unavailable local evidence
or a forbidden verb. Unknown arguments are not echoed.

No internal logs, locks, checkpoints, Git refs, indexes or worktree files are
written. Optional events use explicit **inherited pipe/socket FDs**:
`CARTESIA_EVENT_SINKS=fd:3,fd:4`. The caller opens/passes those descriptors; this
package never opens files, connects sockets or chooses network destinations.
Only version, event name, operation and state are emitted. Invalid sinks reject
before inspection; failed deliveries report a static stderr warning. Other sink
URI types need an external adapter, not a silent fallback to stdout.

## Validation / limits

Fixture tests cover malformed/duplicate JSON, stdin, Unicode paths, shared-index
preservation, feature branches, source-status races, symlinks/nested repos,
forbidden mutations, remote mismatch, dangerous Git filters/fsmonitor/ambient
Git variables, fake GitHub overlap/failure/partial metadata, sibling worktrees,
private/public output and multi-sink redaction. Tests never reach real remotes.

Future publication requires separate approval, content/history review, isolated
publisher transactions, durable pending batches/retry, race-safe capture, remote
acknowledgement and configured host/timezone/branch/roots. None is implied by a
successful dry-run or this installer.
