# `aos job run`

```sh
nohup aos job run --target-sid "$COORDINATOR_SID" --label lane-worker \
  --summary "$RESULT_FILE" -- bash "$CHAIN_SCRIPT" </dev/null >"$LOG_FILE" 2>&1 &
```

Wrap the entire chain, not just its final worker, so the wait is visible. For a direct Pi launch, put `pi --mode json -p ...` after `--`. Use `exec` or propagate the worker exit code from shell chains. The wrapper does not background itself; redirect its stdin in detached use. Interactive commands and commands that initiate their own detached processes are unsupported.

Records go in the selected coordinator’s session inbox (`--inbox` overrides its directory); the existing consumer routes terminal events according to the coordinator’s current steering settings. The status is replaced atomically and the JSONL journal retains transitions. No command args or output are copied to records. Use disclosable labels and artifact paths. No report is generated at the summary path by the wrapper.

`TERM`/`INT` are forwarded to the child process group; a normal command exit is preserved, a signal exit is `128 + signal`. Hard kills and host loss cannot emit a terminal event. Treat stale heartbeats as ambiguous; verify the actual worker before retrying.

## Case decisions (one-shot Pi only)

Add `--case-dir "$CASE"` before `--`. The child must be `pi -p` with the task as its last argument. The wrapper prepends the explicit, trusted case's `decisions.md` (UTF-8, max 16 KiB). Use non-secret content: the combined text is visible in Pi's arguments and goes to the model, but is not stored in bus records. No implicit directory discovery or changes to the existing `subagent` tool.

## Build journal and successful successors

```sh
aos builds --journal "$JOURNAL" --case "$CASE_ID" --label "$LANE"
aos chain --journal "$JOURNAL" --label "$LANE" --build-id "$BUILD_ID" \
  --claims "$CLAIMS" --timeout 7200 -- bash "$SUCCESSOR"
```

Use one trusted watcher journal per case/provider scope. `builds` makes no provider requests; it reads `build-found`, `status` and `terminal` events keyed by `label` and `uuid`. A terminal success is required, not a status-only observation. Use the exact build ID from the submit receipt, never the latest row for a label. `chain` gates a local follow-on command; it is not a build submitter. Put `aos job run ... --` outside `aos chain ...` to track the waiting interval too.

Claim directories must be shared by all candidate chainers for that case and filesystem. A claim intentionally survives errors and process loss; inspect receipts and running processes before clearing one. Return codes before execution: 3 already claimed, 4 terminal non-success, 124 timeout, 2 bad input or local error. Follow-on exit codes otherwise pass through.

Uninstalled tests: `python3 bin/aos-job/test_run.py` and `python3 bin/aos-job/test_builds.py`.
