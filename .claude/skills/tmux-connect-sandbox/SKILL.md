---
name: tmux-connect-sandbox
description: Use tmux-connect's --sandbox mode to reach a named rootless-podman sandbox on a remote host, and non-interactively observe/drive what's happening inside it (an agent's Bash tool cannot do a real interactive tmux attach). Use when asked to connect to, inspect, or run commands in a remote podman sandbox via tmux-connect.
user-invocable: true
argument-hint: "<host> <sandbox> [session]"
---

# tmux-connect --sandbox

## When To Load This

This skill is verbose (ssh/tmux/podman recipes + two documented gotchas) and only earns its context cost in a consumer context that actually does remote host/sandbox operations — not every Claude Code session or agent profile needs it loaded. A narrow, single-purpose worker with no remote-host access shouldn't carry it. On a machine running a larger multi-profile agent fleet, which profile(s) get this skill installed/loaded is that fleet's own decision, layered on top of this generic skill — this file is not "always load me."

## Syntax reference

```
tmux-connect --sandbox --ls [host]          # list running sandboxes on host (default: local)
tmux-connect --sandbox <host> --ls          # same, explicit host
tmux-connect --sandbox <host> <sandbox>     # attach/create tmux session "home" inside sandbox
tmux-connect --sandbox <host> <sandbox> <session>   # named session instead of "home"
tmux-connect --sandbox <host> <sandbox> --ls        # list tmux sessions inside the sandbox
```

`<host>` is whatever this machine's `tmux-connect` host registry knows (or `local`/`mac`). `<sandbox>` is the podman container name on that host. Sandbox and session names are validated against `^[A-Za-z0-9._:@-]+$` — anything else is rejected before it reaches ssh/podman.

## Pitfall: `PROFILE_DIR=... source wrapper.sh` does not persist

An env-var prefix (`VAR=val cmd`) scopes **only that one command**. If a wrapper needs a non-default `tmux-connect` build (e.g. an unreleased branch adding `--sandbox`), sourcing it with a prefixed var does not leak `PROFILE_DIR` into the shell that runs afterward — the next `tmux-connect` invocation silently falls back to the default `PROFILE_DIR` and the default binary, which may not understand `--sandbox` as a flag at all.

Symptom: `Unknown host: --sandbox` — the fallback binary treats `--sandbox` as the first positional arg (host name), then fails host lookup on the literal string `--sandbox`.

```bash
# WRONG — PROFILE_DIR only applies to the `source` command itself
PROFILE_DIR=/path/to/alt/build source some-wrapper.sh
tmux-connect --sandbox <host> <sandbox>
# => Unknown host: --sandbox   (fell back to default tmux-connect)

# RIGHT — export as its own statement first, in the same shell
export PROFILE_DIR=/path/to/alt/build
source some-wrapper.sh
tmux-connect --sandbox <host> <sandbox>
```

If nothing sources a wrapper and you're calling `tmux-connect` directly, just make sure `PATH`/`PROFILE_DIR` resolve to the build that actually has `--sandbox` before running anything — check with `command -v tmux-connect` and confirm `--sandbox` appears in its own `--help` output.

## The core problem: attach mode is built for a human

`tmux-connect --sandbox <host> <sandbox> [session]` (no trailing `--ls`) foregrounds an `ssh -t` + `tmux new-session -A` — it's an interactive attach. Run directly via a one-shot non-interactive Bash tool call, it will hang waiting on a pty or return garbage/truncated control sequences. Do not run bare attach mode as a single agent Bash call.

Two working patterns, pick based on what you need:

- **Recipe A** — you need to interact with a live tmux session inside the sandbox (long-running job, someone else's shell, a REPL). Drive it from a scratch tmux window.
- **Recipe B** — you just need to inspect sandbox state (files, processes, packages). Skip tmux entirely; one-shot `ssh` + `podman exec`. Prefer this whenever it's sufficient — it's simpler and works even if the sandbox has no tmux installed.

## Recipe A: drive an attach non-interactively via a scratch tmux window

Never attach in the agent's own pane. Open a separate window in a tmux session you (the agent) already have shell access to, send keys into it, and read it back with `capture-pane` — exactly like reading over someone's shoulder.

```bash
# 1. Open a scratch window (not the agent's own pane)
tmux new-window -t <agent_session> -n <label>

# 2. Drive it
tmux send-keys -t "<agent_session>:<label>" "tmux-connect --sandbox <host> <sandbox> <session>" Enter

# 3. Give it a moment to connect + render, then read non-interactively
sleep 2
tmux capture-pane -t "<agent_session>:<label>" -p

# 4. Send further commands into the now-attached remote session the same way
tmux send-keys -t "<agent_session>:<label>" "whoami" Enter
sleep 1
tmux capture-pane -t "<agent_session>:<label>" -p

# more scrollback if a command's output got cut off:
tmux capture-pane -t "<agent_session>:<label>" -p -S -200

# 5. Clean up
tmux kill-window -t "<agent_session>:<label>"
```

Notes:
- `sleep` between send and capture is required — ssh/tmux/podman connect latency means an immediate capture reads a stale/blank pane.
- If `capture-pane` shows nothing useful, increase the sleep before re-capturing rather than resending the command (resending can double-submit into a live shell).
- This is for *driving a live session*, not for state inspection — use Recipe B for that.

## Recipe B: direct one-shot recon (preferred for read-only inspection)

```bash
ssh <host> "podman exec <sandbox> bash -lc '<command>'"
```

More reliable than scripting an interactive attach for read-only checks, and works even when the sandbox has no tmux at all.

### Pitfall: no parentheses in echoed section headers

Inside `bash -lc '...'` nested under an outer double-quoted ssh command, an unescaped `(`/`)` in an echoed label breaks the nested quoting:

```bash
# WRONG — causes: syntax error near unexpected token `('
ssh <host> "podman exec <sandbox> bash -lc 'echo === env (sanitized) ==='"

# RIGHT — no parens in the label
ssh <host> "podman exec <sandbox> bash -lc 'echo ---env-sanitized---'"
```

Use `---label---` (or similar paren-free markers) for every section header in these payloads.

### Ready-to-copy probe block

```bash
ssh <host> "podman exec <sandbox> bash -lc '
echo ---whoami-id---
whoami; id
echo ---os-release---
cat /etc/os-release 2>/dev/null || echo missing
echo ---env-sanitized---
env | grep -Ev \"TOKEN|KEY|SECRET|PASSWORD|CRED\" | sort
echo ---ps---
ps aux --sort=-pcpu | head -30
echo ---package-managers---
for pm in apt apt-get dpkg dnf yum apk nix devbox; do
  command -v \"\$pm\" >/dev/null 2>&1 && echo \"found: \$pm\"
done
echo ---tooling---
for t in tmux git python3 node curl wget; do
  command -v \"\$t\" >/dev/null 2>&1 && echo \"found: \$t\"
done
echo ---home---
ls -la ~ 2>&1
echo ---mounts---
mount | grep -Ev \"proc|sysfs|cgroup|tmpfs|devpts|mqueue|shm\"
echo ---disk---
df -h
'"
```

Every `$` inside the payload is escaped (`\$`) because the whole thing is one double-quoted argument to the local `ssh` invocation — without escaping, the local shell expands `$pm`/`$t` before ssh ever sees them.

## Checklist

- [ ] Confirmed which `tmux-connect` build is on `PATH`/`PROFILE_DIR` actually has `--sandbox` (check `--help` output) before assuming the flag exists.
- [ ] Used `tmux-connect --sandbox --ls [host]` / `tmux-connect --sandbox <host> --ls` to confirm the sandbox exists before attaching.
- [ ] For read-only inspection: went straight to Recipe B (`ssh ... podman exec ... bash -lc '...'`), not a scripted attach.
- [ ] For driving a live session: used a scratch tmux window (`new-window` + `send-keys` + `capture-pane`), never a raw one-shot Bash call against attach mode.
- [ ] No parentheses in echoed section headers inside nested-quoted remote payloads.
- [ ] Cleaned up scratch tmux windows after use.
