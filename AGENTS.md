# Profile Repo Agent Rules

## Isolation / Blast Radius

- Default to containerized or isolated-worktree workflows for agentic changes.
- Do not mount host credentials into containers by default: SSH keys, cloud creds, kubeconfigs, browser profiles, 1Password, or full host `$HOME`.
- Use disposable HOME directories for agent containers.
- Prefer read-only mounts for reference repos.
- Run `just ansible-plan` before any host mutation.
- Host mutation requires explicit opt-in: `PROFILE_ALLOW_HOST_MUTATION=1 just ansible-apply`.
- Tool installs require explicit opt-in: `PROFILE_INSTALL_TOOLS=1 TOOLS='["tool"]'`.

## Repo Boundary

- This repo is personal dev tooling only.
- Do not commit secrets, local inventories, machine-specific paths, or employer/customer/project context.
