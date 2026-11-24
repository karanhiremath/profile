# `aos job run`

```sh
nohup aos job run --target-sid "$COORDINATOR_SID" --label lane-worker \
  --summary "$RESULT_FILE" -- bash "$CHAIN_SCRIPT" </dev/null >"$LOG_FILE" 2>&1 &
```

Wrap the entire chain, not just its final worker, so the wait is visible. For a direct Pi launch, put `pi --mode json -p ...` after `--`. Use `exec` or propagate the worker exit code from shell chains. The wrapper does not background itself; redirect its stdin in detached use. Interactive commands and commands that initiate their own detached processes are unsupported.

Records go in the selected coordinator’s session inbox (`--inbox` overrides its directory); the existing consumer routes terminal events according to the coordinator’s current steering settings. The status is replaced atomically and the JSONL journal retains transitions. No command args or output are copied to records. Use disclosable labels and artifact paths. No report is generated at the summary path by the wrapper.

`TERM`/`INT` are forwarded to the child process group; a normal command exit is preserved, a signal exit is `128 + signal`. Hard kills and host loss cannot emit a terminal event. Treat stale heartbeats as ambiguous; verify the actual worker before retrying.

Uninstalled smoke test: `python3 bin/aos-job/test_run.py`.
