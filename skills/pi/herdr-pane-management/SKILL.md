---
name: herdr-pane-management
description: Manage Herdr panes from inside a running Pi/Herdr session. Use when opening, splitting, focusing, moving, or monitoring work in Herdr panes/tabs from within pi. Includes safe socket/server preflight and split-brain recovery checks.
user-invocable: true
argument-hint: "open pane|start poller|diagnose herdr"
---

# Herdr Pane Management

Use this skill whenever operating Herdr from inside Pi, especially when the user asks to open a pane "in this session/tab/workspace".

## Critical safety rules

1. **Never start `herdr server` blindly from inside a Herdr/Pi pane.**
   - If `HERDR_ENV=1`, this process is already inside a Herdr client session.
   - Starting another `herdr server` can steal the canonical socket path and create hidden panes in a different server model.
2. **Always split from the current pane ID, not just workspace/tab IDs.**
   - Use `${HERDR_PANE_ID}` as the split anchor.
   - Workspace/tab IDs can be stale after server restore; current pane anchoring is the visible-session invariant.
3. **Verify visibility with `herdr pane layout --pane "$HERDR_PANE_ID"`.**
   - The new pane must appear in the same layout as the current pane.
4. **If Herdr CLI says connection refused, do not spawn a new server until split-brain checks are complete.**

## Preflight

Run this before creating panes:

```bash
env | sort | rg '^HERDR' || true
herdr status || true
herdr pane current --current || true
herdr pane layout --pane "${HERDR_PANE_ID:?HERDR_PANE_ID missing}" || true
```

Expected inside Pi/Herdr:

- `HERDR_ENV=1`
- `HERDR_PANE_ID=<workspace>:p...`
- `HERDR_TAB_ID=<workspace>:t...`
- `HERDR_WORKSPACE_ID=<workspace>`
- `herdr pane current --current` returns the same pane as `HERDR_PANE_ID`

## Open a visible pane in this session

Preferred direct split:

```bash
PANE_JSON=$(herdr pane split "${HERDR_PANE_ID:?}" \
  --direction right \
  --ratio 0.38 \
  --cwd "$PWD" \
  --focus)
PANE_ID=$(printf '%s' "$PANE_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["result"]["pane"]["pane_id"])')
herdr pane rename "$PANE_ID" '<label>'
herdr pane run "$PANE_ID" '<command>'
herdr pane layout --pane "${HERDR_PANE_ID:?}"
herdr pane process-info --pane "$PANE_ID" || true
herdr pane read "$PANE_ID" --lines 60 --source recent-unwrapped --format text || true
```

Notes:

- Use `python3`, not `python`, for JSON parsing.
- `herdr agent start --tab ... --workspace ...` can create panes, but for "this session" prefer `herdr pane split "$HERDR_PANE_ID"`.
- If the pane command is long-running, use `herdr pane process-info` to verify it is active even if screen text is blank due clear-screen control sequences.

## Start a cbuild async poller pane

```bash
RUN_ROOT='<run-root>'
PANE_JSON=$(herdr pane split "${HERDR_PANE_ID:?}" \
  --direction right \
  --ratio 0.38 \
  --cwd /home/karan.hiremath/src/cartesia-security-worktrees/cbuild-mirror-scan-gate-20260625 \
  --focus)
PANE_ID=$(printf '%s' "$PANE_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["result"]["pane"]["pane_id"])')
herdr pane rename "$PANE_ID" cbuild-poller
herdr pane run "$PANE_ID" "cd /home/karan.hiremath/src/cartesia-security-worktrees/cbuild-mirror-scan-gate-20260625 && scripts/infra/cbuild async watch --run-root $RUN_ROOT --interval 15 --tail 40 --jsonl --hold"
herdr pane layout --pane "${HERDR_PANE_ID:?}"
```

## Split-brain detection

Symptoms:

- `herdr pane split` reports success, but the user cannot see the pane.
- `herdr pane list` shows panes not visible in the UI.
- Multiple `herdr server` processes exist.
- `herdr status` reports not running while a Herdr client is visibly active.
- `connect(.../herdr.sock) = ECONNREFUSED` even though `ss` shows a listener.

Diagnostic commands:

```bash
ps -ef | rg '[h]erdr'
ss -xlpn 2>/dev/null | rg 'herdr.sock|herdr-client.sock|herdr' || true
fuser -v ~/.config/herdr/herdr.sock ~/.config/herdr/herdr-client.sock 2>&1 || true
find /proc/$(pgrep -n herdr)/fd -maxdepth 1 -type l -printf '%f %l\n' 2>/dev/null | rg 'socket|herdr' || true
```

If split-brain is suspected:

1. **Stop creating panes.**
2. Identify duplicate headless servers started by the agent.
3. Prefer `herdr server stop` if the CLI can reach the intended server.
4. If the CLI cannot reach the server, do not kill Herdr processes without explicit user approval unless continuing would create hidden state. Record exactly which PID is being killed and why.
5. After recovery, confirm:

```bash
herdr status
herdr pane current --current
herdr pane layout --pane "${HERDR_PANE_ID:?}"
```

## Operational checklist

- [ ] Confirm `HERDR_ENV=1` and capture `HERDR_PANE_ID`.
- [ ] Confirm `herdr pane current --current` works.
- [ ] Use `herdr pane split "$HERDR_PANE_ID"`, not a guessed tab/workspace.
- [ ] Rename the pane.
- [ ] Run the command.
- [ ] Verify `pane layout` shows both old and new pane in one layout.
- [ ] Verify the command with `pane process-info`.
- [ ] If the user cannot see it, immediately check for server split-brain before retrying.

$ARGUMENTS
