---
name: herm-eikon-defaults
description: Set, restore, or troubleshoot Herm avatar defaults across profiles and sibling seats. Use when the wrong eikon appears, Ares is missing, a new Cos seat loses its avatar, or an eikon selection does not survive relaunch. Not for changing terminal colors or authoring animation assets.
---

# Herm eikon defaults

Scope selection and assets together. Setting `eikon: ares` without installing its packed file can silently render a fallback avatar.

## Inspect first

- Resolve the launcher/profile and its isolated root. Read `active_profile` to locate the actual runtime home; do not assume `~/.hermes` is the seat.
- Read only `herm/tui.json` and eikon package metadata. Do not read `.env` or auth files.
- Check both root and runtime `eikons/<name>/<name>.eikon`. An existing active preference is not proof the file exists.
- Default for CoS-W is **Ares**. Keep the Nighttide theme: avatar selection and theme are independent.
- Discover installed commands with `herm eikon --help`; use `--json` for inspect/info/list/install/use. Catalog lookup can reach external systems; prefer an already-installed local package.

## Set a profile-family default

From the tooling repo, target the resolved root and runtime explicitly:

```sh
bin/hermes/apply-nighttide-theme --home "${AGENT_HOME:?}" --home "${RUNTIME_HOME:?}" \
  --eikon ares --set-default --dry-run
bin/hermes/apply-nighttide-theme --home "${AGENT_HOME:?}" --home "${RUNTIME_HOME:?}" \
  --eikon ares --set-default
```

Repeat `--home` for existing sibling root/runtime pairs that the user wants reset. This preserves unrelated TUI preferences. `--profile cosw` currently selects the broader work class, including work librarians; use explicit homes to avoid changing other roles. New sibling homes inherit the parent's selection at materialization.

If assets are missing, use the local package already installed in a parent seat or the installed eikon catalog:

```sh
HERMES_HOME="${RUNTIME_HOME:?}" herm eikon inspect "${EIKON_PACKAGE:?}" --json
HERMES_HOME="${RUNTIME_HOME:?}" herm eikon install "${EIKON_PACKAGE:?}" --json
HERMES_HOME="${RUNTIME_HOME:?}" herm eikon use ares --json
```

Check compatibility/trust before install. Do not bypass an active-package replacement guard; draft under a new name instead. `install` does not activate; `use` does.

## Persistence and inheritance

- `agents up` preserves an existing eikon selection; explicit force-config overrides it.
- New sibling seats inherit the nearest parent's avatar when their YAML has no explicit eikon. Runtime selection wins over parent-root selection. Only avatar selection is inherited, not session IDs or auth.
- Materialization copies the effective selected eikon into the isolated root and runtime libraries. Never launch solely to test this if doing so would stage credentials or disturb a live pane.
- Keep explicit per-profile customizations. Do not rewrite every profile YAML to repair a machine-local default.
- No live-pane restarts, kills, or send-keys. New launches pick up the setting; live refresh behavior needs separate verification.

## Verify

Compare selected name plus packed-file presence in the actual runtime home. Run tooling regressions:

```sh
"${HERMES_PYTHON:?}" tests/test_hermes_eikon_defaults.py
"${HERMES_PYTHON:?}" bin/hermes/test_hermes_agents_persist.py
"${HERMES_PYTHON:?}" tests/test_hermes_sibling_launch.py
```

Report scope, selected avatar, asset presence, persistence tests, and any live-refresh uncertainty. Colors: load `herm-tui-profiles`. New art/animations: load `eikon-build`.
