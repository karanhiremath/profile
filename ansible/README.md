# Ansible Control Plane

Safety defaults:

- inventory is localhost-only by default
- `inventory.local.yml` is ignored
- check mode first: `just ansible-plan`
- apply requires `PROFILE_ALLOW_HOST_MUTATION=1`
- tool installs require `PROFILE_INSTALL_TOOLS=1` and explicit `TOOLS='["git"]'`

Examples:

```bash
just ansible-bootstrap
just ansible-plan
PROFILE_ALLOW_HOST_MUTATION=1 just ansible-apply
PROFILE_ALLOW_HOST_MUTATION=1 just ansible-apply-tags dotfiles
PROFILE_ALLOW_HOST_MUTATION=1 PROFILE_INSTALL_TOOLS=1 TOOLS='["git","tmux","nvim"]' just ansible-apply-tags cli_tools
```
