# Hermes Fleet

Local-only sandbox-manager observability for Hermes.

## Install

```bash
just hermes-fleet
```

## COSW workspace

The sandbox launcher refuses the primary checkout and requires a linked Git
worktree for its only broad read-write mount. Create a dedicated worktree under
`~/src/karan.hiremath-worktrees/cosw-workspace`, or set `COSW_WORKSPACE` to an
existing linked worktree root. The rest of `~/src` is mounted read-only.

The keep-id mapping binds sandbox uid 1000 to the host operator. Manager state,
its Unix socket, and spool fallback therefore remain owner-only (`0700`/`0600`)
instead of relying on world-writable coordination files.

## Start

Start or upgrade the COSW host manager first. Then provide a local Grafana
admin password through the environment and run:

```bash
export HERMES_FLEET_GRAFANA_ADMIN_PASSWORD='<local secret>'
hermes-fleet start
```

- Grafana: `http://127.0.0.1:3034`
- Prometheus: `http://127.0.0.1:9091`
- Redacted local projection: `http://127.0.0.1:9470`

The stack does not configure a public or Tailnet listener. Do not add remote
exposure without a separate authentication and ACL review.

## Data boundaries

- Manager audit records include action, project, bounded identity, outcome,
  duration, request digest, and peer UID.
- Request payload bodies, prompts, completions, credentials, and environment
  dumps are not copied into audit or metric labels.
- Prometheus labels are intentionally low-cardinality.
- Loki receives only the redacted manager audit JSONL.

## Architecture

The Unix socket control plane is authoritative and remains functional if the
observer, OTel Collector, Prometheus, Loki, or Grafana is unavailable.
