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

## Hermes CoS/CoSW voice secrets from 1Password

Personal hosts enable `hermes_voice` by default via `group_vars/personal.yml`.
The role installs a local helper that resolves the shared Cartesia key from
1Password at launch time; it does **not** write the Cartesia API key to disk.
Profile-local `config.yaml` still controls the voice/model.

Shared reference:

```text
op://agent-stack/karan.hiremath-hermes/credential
```

Run/apply only this role:

```bash
TAGS=hermes_voice just ansible-plan
PROFILE_ALLOW_HOST_MUTATION=1 TAGS=hermes_voice just ansible-apply
```

The role installs:

```text
~/.local/bin/hermes-cartesia-env
```

`bin/hermes/agents` automatically calls that helper before launching a profile
whose materialized config uses `provider: cartesia`.

### Personal service-account bootstrap

For personal use, `group_vars/personal.yml` enables creation of a scoped
1Password service account token. The token has read access to `agent-stack` and
is stored in macOS Keychain; it is not committed and is not the Cartesia API key.

Keychain item:

```text
service: Hermes OP_SERVICE_ACCOUNT_TOKEN my.1password.com agent-stack
account: <local user>
```

If the machine is not signed in to 1Password CLI, service-account creation fails
closed with an authorization error. Sign in/unlock 1Password, then rerun the
`hermes_voice` apply command above.
