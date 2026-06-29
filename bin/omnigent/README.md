# Omnigent profile integration

Omnigent is a host-level agent/session runtime for terminalized harnesses such as Claude, Hermes, Pi, and direct `omni run` agents.

## Install / upgrade

```bash
just omnigent
```

The installer uses:

```bash
uv tool install --python /usr/bin/python3.12 omnigent
```

Override the Python binary with `OMNIGENT_PYTHON=/path/to/python` if needed.

## Personal-safe local default

Use the local persistent server by passing an empty server URL:

```bash
omni server status
omni host status --server ""
omni run --harness claude-sdk --server ""
omni claude --server ""
omni hermes --server ""
omni pi --server ""
```

## Doctor

```bash
bin/omnigent/doctor
```

The doctor prints only non-secret status: binary paths, version, config summary, server status, and host status. It does **not** read log bodies, `chat.db`, artifacts, transcripts, credentials, or session contents.

## State boundary

Shared profile tooling lives here in `~/src/profile`:

- installer
- doctor/status wrapper
- generic launcher documentation
- generic fleet/registry metadata

Machine-local state stays out of git in `~/.omnigent`:

- `config.yaml`
- `chat.db*`
- `logs/`
- `artifacts/`
- daemon/server metadata
- host ids and session ids
- remote server URLs or credentials

Treat Omnigent logs, artifacts, and database rows as potentially sensitive transcript data. Inspect them only for an explicitly personal-scoped debugging task.
