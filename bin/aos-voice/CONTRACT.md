# Offline voice conference contract v1

This is a test adapter, not a replacement session registry, policy engine,
event bus, tmux controller, terminal emulator or voice provider.

## Input and output

All non-help commands emit one JSON object. Help/diagnostics are stderr-only.
Each mutation consumes `aos.voice.conference.v1` from stdin. Extra keys,
duplicate JSON keys, non-finite numbers, wrong schemas and oversized inputs are
rejected. Maximum input: 128 KiB; catalog: 128 nodes; replay history: 128 IDs.
No automatic eviction; start a new explicit fake test when full.

`targets` consumes `aos.voice.catalog.v1`:

```json
{"schema":"aos.voice.catalog.v1","targets":[{"id":"controller","domain":"personal","host":"demo-local","profile":"chief-of-staff","role":"cos","harness":"hermes","session":"demo","generation":1,"parent":null,"capabilities":["status","observe"],"tmux":{"server":"default","session":"$1","window":"@1","pane":"%1"}}]}
```

- `host`/`tmux.server` are registry identities, not addresses/socket paths.
- All tmux IDs are stable IDs, not mutable display names or pane indexes.
- `session` is the harness-session identity (or fixture identity for a plain shell).
- `generation` is a positive safe integer, not a boolean. Changing any ancestor
  or leaf identity, location, generation or capabilities invalidates the pin.
- Domains: `personal`, `work`; a route cannot cross domains. Personal fixtures
  reject work-profile names; this is not a substitute for live domain policy.
- Roles: `cos`, `pm`, `pl`, `worker`, `terminal`. Root must be `cos` and rank
  strictly increases on each hop. Intermediate roles may be skipped.
- Harnesses: `hermes`, `pi`, `codex`, `claude`, `none`. Names describe fixture
  metadata, not implemented adapters. `none` requires `terminal` role and only
  `status`/`observe` capabilities.
- Children cannot widen parent capabilities. Duplicate target IDs or duplicate
  complete tmux locators are ambiguous and rejected.

`bind --fake --domain personal --target remote-worker --generation 3` stores an
independent copy of every route hop. A connected conference cannot be rebound;
leave first. Every later action revalidates the entire route against the supplied
catalog. There is no implicit focus tracking or cross-domain fallback.

`dispatch --fake --request <request_json>` consumes a separate simulated managed
voice-agent callback:

```json
{"schema":"aos.voice.tool.v1","id":"demo-turn-1","target":"remote-worker","generation":3,"verb":"status"}
```

Allowed verbs: `status`, `observe`, `steer`, `draft`. `steer`/`draft` require an
additional `text` string (1–4096 characters). Other verbs reject `text`. Text is
consumed in memory and never echoed, persisted or added to events. Do not use
real transcripts or secrets in fixtures, IDs, command arguments or metadata.

Callbacks must match the exact bound leaf and generation, be permitted at every
hop, and have an unseen request ID. All acknowledgements are explicitly marked
`simulated_accepted`/`simulated_completed`. They prove no actual remote delivery.
Receipts always include `executed:false`; no live backend exists.

`--dry-run` validates the same constraints but changes only the receipt. It does
not join, leave, bind, add replay IDs or emit simulated ACKs. Explicitly configured
side-channel event files may still receive a `dry_run` event.

## Events

Optional configuration (zero sinks by default):

```bash
CARTESIA_EVENT_SINKS='[{"type":"file","path":"<event_file>"}]' \
  ./bin/aos-voice/aos-voice status
```

- `CARTESIA_EVENT_SINKS`: JSON list of `{type:file,path:...}` objects.
- `CARTESIA_EVENT_BUSES`: comma-separated file paths; `CARTESIA_EVENT_BUS`: one path.
- All configured sources combine; duplicate absolute paths are deduplicated.
- Maximum 32 sinks. Parent directories must already exist. Only regular files
  may be appended; final symlinks/FIFOs/devices are rejected without blocking.
- Only named profile `none` is supported offline. Network, stdout and stderr
  sinks are unavailable; unsupported configurations fail closed.
- Events use `cartesia.event.v1` with mode/execution metadata only. No transcript,
  terminal output, profile/host/session IDs, user arguments or raw error text.
- Fanout is append-only, not transactional: earlier sinks may contain the event
  if a later sink fails. Events are never pipeline authority.

## Renderer seam

`Renderer.feed(target,generation,bytes)` and
`Renderer.resize(target,generation,cols,rows)` define the adapter seam. The fake
implementation retains opaque bytes in memory, enforces a 1 MiB bound and a
1–1000 cell viewport. Tests preserve split UTF-8 and alternate-screen escapes
without parsing or interpreting them. This is **not** terminal-fidelity validation.

A real browser libghostty/WASM adapter must implement the seam, maintain the same
pin, and independently pass Unicode/alternate-screen/resize/render tests. WASM
terminal rendering is distinct from the historical Rust/WASI routing component.
Neither renderer is allowed to mint capabilities, discover credentials, connect
SSH or write into a live agent. Operator PTY input and voice tool dispatch must
remain separate authorized channels.

## Live requirements (not implemented)

- Registry-backed remote host/server/session discovery; unregistered sessions
  need explicit adoption before control. No blanket access to every tmux server.
- Authenticated operator and managed-agent tool identity; bounded child grants;
  server-side replay/ACK storage and reconnect/session-generation reconciliation.
- Domain-approved managed-agent endpoint and short-lived brokered credentials.
  Long-lived secrets must not enter browser/WASM code or tool payloads.
- Local microphone consent, visible capture state, bounded context grants and
  sanitized speech only. No terminal-screen/hidden-reasoning capture by default.
- Barge-in stops audio playback/capture, never a build or underlying agent job.
  Revocation or a stale session must release local audio resources even when
  further control requests are rejected.
- Multi-participant conferencing, real audio transport and remote PTY streaming
  are not part of this spike. `join` simulates one operator binding only.
