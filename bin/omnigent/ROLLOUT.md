# Omnigent rollout checklist

Use this to enable Omnigent consistently on each personal/dev machine.

## 1. Pull profile tooling

```bash
cd ~/src/profile
git pull --ff-only
```

## 2. Install or upgrade Omnigent

```bash
just omnigent
```

Expected output includes:

```text
omnigent 0.3.0
omni=...
omnigent=...
Runtime state: ~/.omnigent (machine-local; do not commit)
```

If `/usr/bin/python3.12` is unavailable, set:

```bash
OMNIGENT_PYTHON=$(command -v python3) just omnigent
```

## 3. Start/verify the local server and host

```bash
omni server start
omni host status --server ""
bin/omnigent/doctor
```

If the host shows `offline` or launch requests time out:

```bash
omni host stop --server "" || true
omni server stop || true
omni server start
omni host --server ""
```

For the long-running `omni host --server ""` command, keep it in a managed terminal/tmux pane, or launch it through your terminal supervisor. It is expected to keep running.

## 4. Smoke test

```bash
omni run --harness claude-sdk --server "" --no-log -p \
  "Personal-toolkit smoke test. Reply exactly: OK_OMNIGENT_PERSONAL_SMOKE"
```

Success is the exact response:

```text
OK_OMNIGENT_PERSONAL_SMOKE
```

## 5. Daily usage patterns

Use Omnigent when you want persisted/resumable/forkable terminal-agent sessions:

```bash
omni run --harness claude-sdk --server ""
omni run --harness codex --server ""
omni claude --server ""
omni hermes --server ""
omni pi --server ""
```

Use direct CLIs for quick one-off tasks where Omnigent session persistence is unnecessary.

## 6. State and boundary policy

Keep these machine-local and out of git:

- `~/.omnigent/config.yaml`
- `~/.omnigent/chat.db*`
- `~/.omnigent/logs/`
- `~/.omnigent/artifacts/`
- daemon metadata, host IDs, session IDs
- credentials or remote server URLs

Treat logs, artifacts, and database rows as transcript-bearing sensitive data. Inspect them only for an explicitly scoped debugging task.

Personal profile default: always use the local server (`--server ""`). Work profiles must define their own work-data retention and remote-server policy inside the work boundary.
