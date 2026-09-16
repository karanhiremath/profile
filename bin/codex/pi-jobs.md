# Pi completion hooks

`pi-jobs.py launch -- <approved pi arguments>` starts a detached pi job using the
pi job-status schema and returns its status and output paths immediately.
It reads `CODEX_THREAD_ID`, or accepts `--session-id`. The caller supplies the
worker's approved model, tools, extensions, prompt, and isolated working directory;
the launcher does not grant or bypass permissions. It makes no provider calls itself.

Install the script in a stable local path and append a `PostToolUse` handler to
the user Codex `hooks.json` (preserve existing handlers):

```json
{"matcher":"*","hooks":[{"type":"command","command":"python3 ~/.local/lib/codex/pi-jobs.py hook","timeout":3,"additionalContextLimit":1000}]}
```

Review and trust the new definition in Codex `/hooks`. The hook reads only this
session's pi status records. Each completed job produces one bounded status pointer;
running jobs produce nothing. The model must inspect and validate worker artifacts.
Existing pi bus consumers keep their own acknowledgements.

Notifications arrive when another tool completes; this hook does not wake an idle
thread. It does not attach to existing untracked pi processes or restart them.
