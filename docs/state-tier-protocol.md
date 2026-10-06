# Tiered State Protocol for Hermes/cosw Sessions

status: draft v1 — for review, no code yet
owner: karan.hiremath
motivating incident: state.db SQLITE_PROTOCOL wedge (stale NLM holder `cxis-devlarge-2 pid=376506`, Sep 15; foreign writer pid 2093, host unknown)

## Problem

One profile home on shared NFS (`/shared` → symlink to `/data_vast`, same volume)
is opened by gateways on multiple hosts. SQLite multi-host-over-NFS is unsupported;
crashes leave NLM locks dangling; holder identity is an advisory file with no TTL.
Result: recurring `SQLITE_PROTOCOL` wedges that block every `cosw` launch.

Ground truth (observed 2026-09-24):
- `/shared/people/karan.hiremath` ≡ `/data_vast/people/karan.hiremath` (symlink). One volume.
- `/home` is also NFS (`cxis-data-0:/home`) — host-local disk must be verified before relying on it (needs-check).
- state.db schema splits cleanly into ephemeral / durable-transcript / singleton classes.
- Precedents to reuse: `fork-sync` (validate→promote), `notes-ledger` (two-ledger append),
  `cosw-host-control` daemon (0.2s tick), `state_doctor.py` (fresh stores pinned to journal_mode=delete).

## Tier model

| Tier | Scope | Store | Writer model | Read model | Conflict rule |
|---|---|---|---|---|---|
| **T1** | Interactive TUI session (per session UUID) | `state.<session_uuid>.db` shard | Single writer = the process owning the session (host+pid lease) | Only the owning session; no cross-session reads | None — single writer by construction |
| **T2** | Background sessions (per session UUID) | Same shard format, separate lane | Single writer per shard; longer TTL lease; may outlive TUI | Owning session + job-bus/spool consumers | None per shard; ordering resolved at spool drain |
| **T3** | Profile definitions + memory layers (fleet-wide, all profiles, all hosts) | Git-backed canonical repo (`agentic/memory`, profile repo) | Single-writer promotion lane (validate→promote, fork-sync pattern) | All sessions via version-stamped symlink path | Last-validated-wins; append-only ledgers for lessons; never force-push |

### T1 — interactive session shards

- One SQLite DB per TUI session UUID. Session UUID is the shard key.
- Owner holds a **lease** (heartbeat + TTL) in a small NFS registry DB
  (`registry.db`, journal_mode=delete, short transactions). Lease record:
  `session_uuid → {host, boot_id, pid, shard_path, expires_at, seq_watermark}`.
- Stale holders self-expire: takeover = lease expiry, not manual cleanup of
  `.gateway.lock.holder`-style files (those are retired).
- journal_mode: WAL if shard lives on verified host-local disk; delete if on NFS.
- Schema classes placed in the shard:
  - ephemeral: `session_turn_leases`, `compression_locks`, `gateway_hygiene_state` — TTL-expire, never reconciled
  - durable transcript: `sessions`, `messages`, `messages_fts*`, `session_model_usage` — append with `(session_uuid, seq)` monotonic keys

### T2 — background sessions

- Identical sharding; differences are lifecycle, not format:
  - heartbeat cadence lower (e.g. 30s) but TTL generous (bg sessions legitimately idle)
  - cross-session delivery goes **only** through spool/job-bus (idempotent, acked),
    never direct writes into another session's shard
  - shard drain on session end + periodic reconcile sweep (host-control daemon already ticks at 0.2s; it is the natural sweep carrier)
- Ephemeral `gateway_heartbeats` stays per-writer; delivery obligations live in the
  spool, not the shard, so a crashed bg session never strands fleet state.

### T3 — shared layers and the self-improvement loop

Two layers, both git-backed, both provisioned read-only to sessions:

1. **Profile definitions**: cosw seats/flags/agents/plugins (profile repo).
2. **Memory layers**: `~/src/karan.hiremath/agentic/memory` (playbooks, projects,
   lessons, brain, FLEET.md, SESSION-INDEX.md) — already git-origin'd to
   `cartesia-ai/karan.hiremath`.

Protocol:
- **Write path**: sessions never write T3 directly. Lessons/observations go to an
  append-only intake ledger (notes-ledger pattern, content-hash dedupe).
- **Promote path**: intake → validate (fork-sync `validate` pattern: sandbox run,
  then `origin/validated/main`) → ff-only promote to origin → nightly refresh fans
  out to hosts (`fork-sync nightly/install-nightly` already exists).
- **Read path**: sessions read via a short, stable symlink path
  (also fixes the AF_UNIX 128>108 tick-socket failure).
- **Hot reload**: every tier-3 asset carries a version stamp (git SHA + mtime).
  Running sessions re-check the stamp at turn boundaries and reload on change —
  self-improvement reaches *currently running* sessions; future sessions pick it
  up at provision. No session restart needed.
- **Profiles × hosts × memory matrix**: profile defs select which memory layers
  apply per profile; fanout is per (profile, host) pair, tracked in FLEET.md /
  SESSION-INDEX.md.

### Reconciliation

- T1/T2 shards merge durable-transcript tables into a canonical profile store
  (or remain sharded-forever behind a query index — open decision D2).
- Merge is idempotent upsert on `(session_uuid, seq)`; FTS rebuilt at merge time.
- Singleton tables (`state_meta`, `gateway_routing`, `hosted_room_*` (~15 tables),
  `delivery_obligations`) are **not** sharded: one elected writer per profile via
  lease. These have cross-writer ordering (watermarks, policy cursors) that must
  not be merged.
- Spool drain (existing machinery, currently 3 pending) is the T2→T1/T3 bridge.

## Table→tier map (from actual state.db schema)

| Tables | Tier |
|---|---|
| `sessions`, `messages`, `messages_fts*`, `session_model_usage`, `sqlite_sequence` | T1/T2 shard (durable) |
| `session_turn_leases`, `compression_locks`, `gateway_hygiene_state`, `gateway_heartbeats` | T1/T2 shard (ephemeral) |
| `state_meta`, `schema_version`, `gateway_routing`, `hosted_rooms` + `hosted_room_*`, `delivery_obligations` | T3-singleton: elected writer only |
| spool queue, registry | T2 bridge / T1 registry (journal_mode=delete) |
| profile defs, memory layers | T3 git |

## Open decisions (need operator ruling)

- **D1 — shard storage location**: verified host-local disk (WAL ok) vs NFS with
  single-writer + journal_mode=delete. `needs-check`: what is genuinely local on
  cxis-devlarge-* (all current mounts inspected are NFS, including /home).
- **D2 — canonical transcript**: merge shards into one canonical DB vs
  sharded-forever + query proxy (index DB listing session_uuid → shard). Merge
  wins on simplicity; sharded-forever wins on never re-contending.
- **D3 — session affinity**: whether one session may migrate across hosts
  (lease migration) or dies with its host (state drains on end).
- **D4 — T3 promotion gating**: auto-promote validated lessons vs human approval
  gate for playbook/memory edits.
- **D5 — granularity**: per-TUI-session shard (as proposed) vs per-lane shard.

## Rollout

- **P0 (independent of this design)**: offline repair of current wedge —
  fresh store pinned `journal_mode=delete`, short hermes_home symlink
  (AF_UNIX fix), drain 3 spool items, retire stale `.gateway.lock.holder`.
- **P1**: shard mode behind a flag (`COSW_STATE_TIER=shard`), registry.db +
  leases, singleton tier untouched.
- **P2**: reconcile worker + T3 hot-reload stamps; retire lock files.
- Upstream home: `hermes-agent` runtime (schema owner) + profile-bin wrappers.
  Extend existing tests (`test_state_db_repair_non_destructive.py`,
  `test_state_synchronous_pragma.py`, readonly preflight tests).

## Facts vs inference

- Observed: same-volume /shared≡/data_vast, NFS /home, stale holder file,
  SQLITE_PROTOCOL, foreign writer pid, fork-sync/notes-ledger mechanics,
  schema table list (read-only copy of wedged DB).
- Inference: merge complexity of `hosted_room_policy_*` (from table names, not code);
  suitability of host-control daemon as lease carrier (it already ticks 0.2s).
- Unknown: local scratch existence on devlarge hosts; which host runs writer pid 2093.