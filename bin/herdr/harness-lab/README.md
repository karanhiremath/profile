# herdr harness lab

Generic sandbox for evaluating terminal agent wrappers, research CLIs, process supervisors, and runtime adapters before using them in herdr fleets.

This is intentionally generic profile tooling. Keep Cartesia-specific hosts, repos, findings, and approvals in the work memory repo.

## Goals

- install and test wrappers inside an isolated container, not on the host
- capture tool versions, help output, smoke results, and logs
- keep host credentials out of the sandbox by default
- make future wrapper evaluation repeatable

## Runtime

Local default: rootless Podman.

```bash
bin/herdr/harness-lab/scripts/build
bin/herdr/harness-lab/scripts/smoke
bin/herdr/harness-lab/scripts/shell
```

## Operator URL helper

Herdr can capture mouse events, so normal terminal URL clicks may not work inside the TUI. Use the helper to open the newest URL from the focused pane:

```bash
bin/herdr/open-url
bin/herdr/open-url --print
bin/herdr/open-url --copy
bin/herdr/open-url --pane <pane_id>
```

Set `mouse_capture = false` under `[ui]` in `~/.config/herdr/config.toml` to let the outer terminal handle normal URL clicks.

The container includes baseline tooling for:

- herdr/tmux-style terminal agent orchestration experiments
- `llm` + `llm-perplexity` for Perplexity skill validation
- public npm agent-wrapper packages for smoke testing; packages with unsafe lifecycle behavior stay deferred until isolated separately
- process/job supervision helpers such as process-compose and pueue
- evidence collection tools such as jq, git, ripgrep, and basic proc tools

## Secret policy

Default sandbox runs without host secrets.

Allowed only with explicit per-run approval:

```bash
PERPLEXITY_API_KEY=... bin/herdr/harness-lab/scripts/run --allow-perplexity -- llm -m sonar 'hello'
```

Do not mount `~/.ssh`, cloud configs, kubeconfigs, password stores, or full home directories.

## Files

```text
Containerfile                  container definition
manifests/base.yaml            intended tool list and policy metadata
scripts/build                  build local image
scripts/run                    run command in sandbox
scripts/shell                  open interactive shell in sandbox
scripts/smoke                  collect tool versions/help and write artifacts
scripts/validate-manifest      minimal manifest sanity checks
artifacts/                     local smoke outputs, gitignored by convention if desired
```

## Promotion rule

A wrapper is not eligible for herdr/cdev/cagent fleet use until it has:

- pinned source/version or documented reason for using latest
- smoke artifact
- no-secret evidence
- declared network needs
- no host write outside mounted scratch/artifacts
- no hidden kill/cancel/rollback behavior
