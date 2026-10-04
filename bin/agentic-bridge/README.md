# Agentic bridge

Small, local JSONL mailbox for explicitly addressed agent coordination. It does
not launch agents, steer sessions, contact a network service or deliver text to a
terminal. Posting an event means it was durably appended; acknowledgment requires
a separate `ack` or `assignment.accepted` event referencing its event ID.

Use a dedicated runtime directory: append creates it if necessary and sets the
leaf directory to `0700` and the bus to `0600`. Keep runtime buses out of Git.
Use a separate bus for each project and privacy lane. The helper validates every
complete envelope against the requested project and privacy before reading or
appending. Privacy values are `personal`, `work-private`, and `generic`.

```bash
python3 main.py append \
  --bus /absolute/runtime/home-infra/events.jsonl \
  --project home-infra --privacy personal \
  --sender codex --recipient pi-home-infra --kind assignment.created \
  --body-file /absolute/path/to/handoff.md

python3 main.py read \
  --bus /absolute/runtime/home-infra/events.jsonl \
  --project home-infra --privacy personal --limit 20

python3 main.py append \
  --bus /absolute/runtime/home-infra/events.jsonl \
  --project home-infra --privacy personal \
  --sender pi-home-infra --recipient codex --kind ack \
  --in-reply-to POSTED_EVENT_UUID --message 'Accepted; working on the handoff.'

python3 main.py status \
  --bus /absolute/runtime/home-infra/events.jsonl \
  --project home-infra --privacy personal
```

All successful commands emit one JSON result. Append returns `status: posted`
and the created envelope. Status counts posted and acknowledged events separately;
an acknowledgment does not prove task completion or authenticate its writer.
`read` returns the newest records by default; pass `--after-event-id UUID` to
consume subsequent records in order, then use its returned `last_event_id` as the
next cursor. `has_more` indicates records were omitted by the limit.

Envelopes contain `schema_version: agentic.bridge.v1`, UUID `event_id`, UTC
`timestamp`, `project`, `privacy`, `sender`, `recipient`, `kind`, nullable
`in_reply_to`, and string `body`. Optional `--correlation-id ID` adds a
`correlation_id` for a wider assignment or trace. Body files are UTF-8, up to
64 KiB; `--message` is limited to 2,000 characters. Shell-quote message text or use
`--body-file` for multiline content.

Writers use an exclusive `flock`, append a complete line, flush and `fsync` before
reporting success. Readers hold a shared lock. An incomplete final line is skipped
with `trailing_partial_ignored: true` by readers; append refuses it, including a
valid JSON value missing its final newline. A malformed complete line or duplicate
event ID fails either operation. The helper never truncates or repairs a bus.
Other writers must use the helper or honor the same lock; do not rotate or replace
a bus file while it is in use. Locks have a ten-second acquisition timeout.

Run the tests without dependencies:

```bash
python3 -m unittest discover -s /Users/karan/src/profile/bin/agentic-bridge -p 'test_*.py'
```
