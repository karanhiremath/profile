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

## SSH authorized_keys from 1Password

Add this to `ansible/inventory.local.yml` for each host that should receive the shared public keys:

```yaml
profile_op_account: my.1password.com
profile_ssh_authorized_keys_enabled: true
profile_ssh_authorized_keys_op_ref: "op://<vault>/<item>/public_keys"
```

The 1Password field should contain newline-separated SSH public keys. The role reads it with:

```bash
op read "op://<vault>/<item>/public_keys"
```

Run check/apply for only this role:

```bash
TAGS=ssh_authorized_keys just ansible-plan
PROFILE_ALLOW_HOST_MUTATION=1 TAGS=ssh_authorized_keys just ansible-apply
```

The Ansible task uses `no_log: true` for fetched key material.
