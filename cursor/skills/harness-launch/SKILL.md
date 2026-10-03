---
name: harness-launch
description: Launch or attach an existing harness profile through its canonical alias and registry-backed tmux route, preserving native profile, model, account, and context.
---

Use the existing profile alias as the entry point: `cos`/`cos-m` select the personal Chief of Staff; `cosw`/`cosw-m` select the work Chief of Staff. Retain any selected lane, model, effort, home and resume identity. Other Hermes profiles retain `agents up <profile>`; Claude runs Claude CLI and Pi runs its target-specific native executable. Keep personal and work homes separate.

Load `infra-host` for registry routes. Probe `--ls` first, allowing its declared local cache writes. Existing aliases and normal attach routes reuse their existing sessions; preserve their homes, locks and composers. Instructions belong to alias help/discovery, not a replacement launcher.

The canonical adapter additionally supports an **explicit direct-argv** creation primitive:

```bash
tmux-connect --new-argv <registered-host> <unique-session> \
  --cwd "${HARNESS_CWD:?}" --alias <existing-alias> --profile <selected-profile> \
  --request-id <request-id> --timeout 15 -- "${HARNESS_EXE:?}" <native-argv>
tmux-connect --sandbox --new-argv <registered-host> <running-sandbox> <unique-session> \
  --cwd "${HARNESS_CWD:?}" -- "${HARNESS_EXE:?}" <native-argv>
```

Host aliases may forward `<host> --new-argv ...`; sandbox aliases may forward `<host> <sandbox> --new-argv ...`. Paths are absolute bindings already verified in that target's namespace. Alias/profile fields declare caller identity; they neither select a model nor prove the installed home.

`--new-argv` creates a detached, attachable session and rejects collisions atomically. It directly executes argv through tmux and `/usr/bin/env`; **it does not initialize interactive ZSH**. It cannot satisfy a request requiring normal interactive ZSH initialization. Report that precise gap and use only a reviewed supported alias mechanism; never silently substitute this mode, shell flags, startup edits or terminal input injection.

Preserve native flags verbatim, default permissions and existing accounts. Do not install, upgrade, authenticate, copy context, start containers, send keys, automate trust dialogs or change global tmux options. A control timeout leaves creation uncertain; do not retry, kill or restart the persistent session.

Direct mode rejects inherited agent-custody settings because this source base has no supported custody adapter; it never falls back to raw SSH. Use the existing supported custody route. Route/native input is limited to 256 arguments and 16 KiB before Python or control-client spawn.

The JSON receipt records target, session/pane, cwd/executable, declared alias/profile, source hash, creation outcome and attach argv. It omits prompt argv and raw stderr. Native resume identity, observed model, first response and registration remain unknown until supported native evidence supplies them. An executable/version check, created pane or transport ACK proves none of those outcomes.

Send receipts to the existing kernel adapter only when its supported interface and owner are available and authorized; otherwise return the receipt without creating a bus or controller. Native resume must name the actual session and original cwd; do not infer it from tmux names or replace it with an implicit latest-session resume.
