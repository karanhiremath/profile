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

Uninstalled tests: `python3 -m unittest discover -s bin/aos-job`.

## Candidate readiness → Forge validation

`aos validate-on-ready` is an opt-in, one-shot inbox drain. Run it from the
supervised post-deploy integration or a timer (e.g. every 30s). Do not point it
at a global/mixed inbox. Use a trusted, case-private Pi inbox shared with the
producer and the exact target SID. A build terminal event is not a readiness
event; `aos builds`, `aos chain` and `aos job run` keep their existing semantics.

```sh
set -euo pipefail
# Inject FORGE_API_KEY via the approved secret runner, not argv or a local file.
aos validate-on-ready --inbox "$CANDIDATE_INBOX" --target-sid "$COORDINATOR_SID" \
  --routes "$ROUTES_JSON" --forge-origin "$FORGE_ORIGIN" --state-dir "$DIGEST_LEDGER" \
  --case-dir "$CASE" --receipt-importer "$RECEIPT_STATUS_PY" \
  --temporal-jobs-dir "$CAI_AOS_JOBS_DIR"
```

The operator supplies the HTTPS origin, trusted `receipt-status.py` checkout,
and routes. Example schema (not a shipped default):

```json
{
  "schema": "aos.validate-on-ready.routes.v1",
  "routes": [{
    "infra": "fips", "model": "example-voice", "cluster": "test-cluster",
    "release": "test-release", "component": "worker",
    "repository": "registry.example.test/model/worker",
    "mode": "attach-to-existing-release", "config_ref": "example-voice-attach"
  }]
}
```

Each `config_ref` must be reviewed and already deployed on that Forge origin:
attach-only for the exact target, supporting `overrides.candidate.image` as a
repository-qualified digest and verifying the running digest at attach time.
`mode` records that operator review; the consumer cannot verify registry config
contents before submission. Do not map generic reinstall/ephemeral configs.
No event can supply a destination, config, additional overrides or a command.

Use one durable local digest ledger and owner/drain host across all cases;
do not use per-case ledgers or independent copies. A five-minute gate applies
to new claims. The per-digest claim is committed before POST, and the POST
carries the same deterministic Forge idempotency key. Replay repairs missing
case/cai-aos receipts. Ambiguous failures and HTTP 409 reconcile with a GET of
the deterministic ID; only matching actor/config/effective image are accepted.
Even a 404 or a definite rejection does not cause an automatic retry. Inspect
the Forge run and retained claim before any manual intervention; do not delete
the claim on ambiguity. One digest observed in a different route is reported
as a conflict, not validated twice.

Case receipts appear under `forge-validation-receipts/`. The cai-aos projection
records submission and the workflow ID, not terminal results or release approval.
After both sinks are present, archive handled inbox files via the operator's
normal retention procedure; retain ledger claims. No installer or timer is
changed by this command.
