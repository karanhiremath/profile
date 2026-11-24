# `aos job run`

```sh
nohup aos job run --target-sid "$COORDINATOR_SID" --label lane-worker \
  --summary "$RESULT_FILE" -- bash "$CHAIN_SCRIPT" </dev/null >"$LOG_FILE" 2>&1 &
```

Wrap the entire chain, not just its final worker, so the wait is visible. For a direct Pi launch, put `pi --mode json -p ...` after `--`. Use `exec` or propagate the worker exit code from shell chains. The wrapper does not background itself; redirect its stdin in detached use. Interactive commands and commands that initiate their own detached processes are unsupported.

Records go in the selected coordinator’s session inbox (`--inbox` overrides its directory); the existing consumer routes terminal events according to the coordinator’s current steering settings. The status is replaced atomically and the JSONL journal retains transitions. No command args or output are copied to records. Use disclosable labels and artifact paths. No report is generated at the summary path by the wrapper.

`TERM`/`INT` are forwarded to the child process group; a normal command exit is preserved, a signal exit is `128 + signal`. Hard kills and host loss cannot emit a terminal event. Treat stale heartbeats as ambiguous; verify the actual worker before retrying.

Uninstalled smoke tests: `python3 -m unittest discover -s bin/aos-job`.

## Auth watcher integration

The watcher sends a bounded JSON event on stdin to `aos job auth-event
--target-sid SID` (or `--global-only` before a coordinator is known). The
publisher accepts only fixed event kinds and metadata fields; operator commands
are rendered from fixed templates, not accepted from the caller. Event IDs are
stable across publisher retries.

Urgent `auth.needs-login` and `auth.failed` are terminal-status pointers in the
selected inbox, eligible for model injection on the coordinator's next existing
job-bus poll if auto-steer is enabled. `global:cauth` is an opt-in dashboard lane
and its records are always nonterminal. No live harness changes are required.

`aos atop auth-status --cauth /path/to/cauth` provides a read-only status view
for an atop widget; `--json` emits the same per-session state, expiry, last
probe and check time as structured rows.
