# Fleet reconciliation and session telemetry

`aos fleet` / `aos session` produce JSON only. Diagnostics go to stderr; optional comma-separated `CARTESIA_EVENT_SINKS=file:<path>,file:<path>` receive content-free NDJSON events. Unsupported event sinks fail closed. No credentials, transcript content, profile bytes, or adapter stderr are emitted.

## Profile freshness

```sh
aos fleet discover --manifest "${AOS_TARGET_MANIFEST:?}"
aos fleet reconcile --manifest "${AOS_TARGET_MANIFEST:?}" --check
aos fleet reconcile --manifest "${AOS_TARGET_MANIFEST:?}" --apply
```

Manifest: `aos.fleet-reconcile.v1`, `targets: [{id, command: [executable, ...args], artifacts: [{name, source, destination, expected}]}]`. Check is default. stdin is supported with `--stdin`. Each target command accepts one `aos.fleet-target.v1` request and returns a digest report. Target helper:

```sh
node "${PROFILE_DIR:?}/bin/aos-runtime.mjs" target --root "${AOS_TARGET_HOME:?}" --stdin
```

`fleet discover` sends an observation request through the same approved host commands and enumerates all rootless Podman sandboxes, including stopped containers. Missing Podman/transport is blocked, never empty-success. Discovered sandbox installs remain explicitly unchecked; append approved per-sandbox commands/artifacts to the manifest before reconciliation.

Use existing constrained host/sandbox transport to invoke this helper. There is no raw SSH fallback. Enumerate host-local installation roots and **every sandbox home** in the approved manifest; shared host HOME does not cover independent sandbox homes. Reports explicitly say `coverage: manifest-only`: no blanket fleet freshness claim. Unavailable targets are blocked, not empty. This command is not a daemon or a second fleet controller.

Apply requires committed tracked source and the approved installed predecessor SHA-256 (`expected: null` for an absent file). Divergence is a conflict. Existing files are backed up, source content digest is verified, and installed digest is read back. Symlink destinations and secret-material paths are refused. Approved artifacts are profile/config data, not executable toolchains. No deletion, process restart, lifecycle cancellation, auth provisioning or implicit install. Source-secret detection is defense in depth, not permission to distribute arbitrary unreviewed files.

## Original-kernel binding

```sh
aos session bind --identity "${AOS_IDENTITY:?}" \
  --adapter "${AOS_KERNEL_ADAPTER:?}" --kernel-id "${AOS_KERNEL_ID:?}"
aos session status --session "${AOS_NATIVE_SESSION_ID:?}" \
  --session-file "${AOS_SESSION_JSONL:?}"
```

Identity file schema `aos.identity.v1`: exact native `session_id`, `harness` (`pi|hermes|claude|cursor|codex|devin`), canonical `host`, `profile`, reviewed `profile_digest` (SHA-256), `worktree`, `project`, optional `session_file`. No invented IDs. Adapter is a JSON argv array to the **existing original-kernel owner adapter**, not a shell string. It must be an approved public invocation without secret arguments. Bind is explicit; display polling only observes. Metadata lives at `${AOS_BINDINGS_HOME:-<user-state>/aos/bindings}` with mode 600.

Adapter request schema `aos.kernel-binding.v1`: `op: bind|observe`, pinned `kernel_id`, deterministic `operation_id`, `identity`. Bind receipt must return matching schema, kernel and operation with `accepted: true`. A separate observe must return matching `binding` identity/operation/accepted, `observed_at`, `heartbeat_at` and session/project/kernel-scoped `graph: {kernel_id, session_id, project, nodes, edges}`. Both clocks must be within 30 seconds and not in the future. The adapter must translate these requests through the original core's claim/invoke/independent-verify/heartbeat interfaces. It must not acknowledge based only on an emitted file, local registry or cached topology graph.

Observe may include `telemetry: {schema: "aos.session-telemetry.v1", session_id, observed_at, tokens: {input, output, cache_read, cache_write, total, turns}, context: {used, limit}}`. The original adapter must obtain counters/context from each harness's authoritative native usage API. Telemetry must be session-correlated and fresh; unknown fields are discarded, missing counters stay null. Do not substitute cumulative token totals for context occupancy.

No concrete kernel endpoint is assumed or manufactured. Until the original owner supplies this adapter, sessions remain unbound. A successful source test with an adapter fixture is not runtime registration. After adapter integration, validate real receipt, independent state readback, scope, fresh heartbeat and actual event delivery before rollout.

## Counters and handoff

`aos.session.v1` is display-only. Raw input/output/cache-read/cache-write/provider-total remain separate from context window usage. Missing counters are null, not invented zero. Pi `message` persistence and `message_end` stream logs are supported; persistence wins if both appear, and message IDs are deduped. Context percent is computed only from explicit `context_used/context_max`, never cumulative billed tokens. Handoff reads the existing native Pi prep record; queued does not mean switched. Thresholds remain 60/70/75. Other harness adapters may return `handoff: {schema: "aos.handoff.v1", source_session_id, phase, child_session_id}` in a fresh accepted observation. They must supply actual lifecycle observations rather than infer handoff from compression.

## Publication cadence

Use isolated feature branches. Commit validated milestones and push each checkpoint with `git push origin <feature-branch>`; verify upstream ahead count is zero. Never auto-stage unrelated dirty work, push another owner's branches or force-push shared refs. Runtime installation is separate from branch publication; a pushed patch does not prove every host has adopted it.

Herm can observe this command by native session ID. A switched session must bind independently; no inheritance of its predecessor's identity. Stale/disconnected/unbound states are visible, not proof of registration.

## Validation

```sh
node --test bin/aos-runtime.test.mjs
bash bin/tmux/test-probe-failures.sh
bash bin/tmux/test-tmux-connect-sandbox.sh
```

Tests cover exact identity, readback/heartbeat rejection, both token formats, dedupe, handoff phases, committed source gates, conflicts, backups, path traversal/symlinks/secrets, JSON pipeline cleanliness, fanout and fake check/apply targets.
