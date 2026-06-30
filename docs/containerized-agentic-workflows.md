# Containerized Agentic Workflows SOP

Principle: isolate first; widen only with an explicit reason.

## Defaults

- Run agent/dev workflows in a container or isolated worktree.
- Mount only the repo under work plus a disposable HOME by default.
- Do not mount SSH keys, cloud creds, kubeconfigs, 1Password, browser profiles, or host `$HOME` unless the task explicitly requires it.
- Prefer read-only mounts for reference repos.
- Use `ansible --check --diff` before host mutation.
- Keep Ansible inventory local-only unless intentionally reviewed.

## Blast-radius tiers

| Tier | Use | Filesystem | Network/creds |
|---|---|---|---|
| T0 | read/review | repo read-only | none |
| T1 | code edits | repo worktree read-write, disposable HOME | none by default |
| T2 | local tool install | selected host paths via Ansible | no cloud creds |
| T3 | external systems | explicit plan + approval | short-lived scoped creds only |

## Profile repo policy

- `ansible/inventory.example.yml` is localhost-only.
- `ansible/inventory.local.yml` is gitignored.
- Non-check Ansible runs require `PROFILE_ALLOW_HOST_MUTATION=1`.
- Tool installs are opt-in via `PROFILE_INSTALL_TOOLS=1` and `TOOLS=...`.

## Typical commands

```bash
hs                 # local Hermes/herdr sandbox for the current repo
hs foo             # local Hermes/herdr sandbox for ~/src/foo
hs --status foo    # print resolved repo/profile/session/sandbox boundary
hs --container-shell foo  # container shell with only repo + disposable HOME mounted
just agent-container-build
just ansible-plan
PROFILE_ALLOW_HOST_MUTATION=1 just ansible-apply
PROFILE_ALLOW_HOST_MUTATION=1 PROFILE_INSTALL_TOOLS=1 TOOLS=git,tmux,nvim just ansible-apply-tags cli_tools
```

## `hs` entrypoint

`hs` is the day-to-day Hermes Sandbox entrypoint. Its default mode is optimized
for muscle memory: resolve the project, create disposable sandbox state under
`~/.hs/<slug>/home`, set `HERMES_HOME` inside that HOME, and attach
`herdr --session hs-<slug>` from the project directory. Slugs are compact and
hashed for long project names to stay under macOS Herdr socket path limits.

Default `hs` isolates Hermes/herdr state and HOME-relative files, but it still
runs as a local host process. It is therefore a convenience/state sandbox, not a
filesystem security boundary. The disposable HOME gets a generated minimal zsh
bootstrap (`.zshrc`, `.zprofile`, `.config/.vars`) that sources this repo's shell
profile files without sourcing the host `~/.zshrc`, keeping host secrets/work
snippets out while making profile functions and PATH defaults available. Use
`hs --container-shell <project>` when the task needs the stronger T1-style
boundary of mounting only the repo and disposable HOME into a container.

Use `dream status` for the Dream Sandbox machine entrypoint and `hs --status
<project>` for project-scoped sandbox inspection. Status mode is read-only: it
does not attach tmux/herdr and does not create the disposable HOME.
