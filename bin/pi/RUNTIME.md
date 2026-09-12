# Pi runtime repair and verification

`install-handoff-runtime.mjs` supplies the generic handoff dependency closure:
`jobs.ts`, `job-runner.mjs`, `pi-invocation.ts`, `job-bus-project.ts`, and
`agent-otel.ts`. Copying only top-level extensions can break every Pi startup
when a transitive import is missing. Keep these helpers together.

```bash
node bin/pi/install-handoff-runtime.mjs             # dry-run
node bin/pi/install-handoff-runtime.mjs --apply     # missing files only
node --experimental-strip-types --test bin/pi/*.test.mjs
node bin/pi/toolcall-probe.mjs --model openai-codex/gpt-5.5
node bin/pi/toolcall-probe.mjs --model cursor/grok-4.6:fast --bridge --user-extensions
```

For an isolated Cursor extension check, omit `--user-extensions` and pass
`--extension "${PI_CURSOR_SDK_REPO:?}"`. For another agent directory, set
`PI_CODING_AGENT_DIR`. Startup tests must include both isolated and normal
extension discovery; isolated success does not certify the installed profile.

Installer safety: dry-run by default, validate sources before mutation, reject
symlink destinations, exclusive-create missing files, preserve existing host
overrides. No settings, credentials, sessions, running processes, or model
preferences are changed. An interrupted install is rerunnable. Preserved
files may differ from the bundle and require separate compatibility checks.

The probe performs one live read in a throwaway workspace and verifies the
execution/result pair plus unpredictable file contents. Replay cards and
narrated tool calls do not count as bridge execution. It uses existing
provider credentials without reading or copying them itself, disables project
resources and ambient Cursor settings, and retains no raw model/tool output.
`--user-extensions` loads the operator's trusted global extensions, which may
have their own startup side effects. No timeout/cancellation or automatic retry
is applied; report an in-flight probe rather than claiming completion.

Receipts go to JSON stdout; diagnostics go to stderr. Reported zero cost is
not evidence of free provider usage. This single-read probe is not a resume,
compaction, TUI, full-profile, or upstream release gate.

`pi-session-inspect.mjs <session.jsonl>` reports structural tool/replay/error
metadata only. It does not print prompts, arguments, result bodies, or raw
error messages.
