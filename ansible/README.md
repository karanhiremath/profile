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

## Hermes CoS over iMessage with BlueBubbles

The `hermes_imessage` role makes the Mac mini a repeatable, private iMessage
bridge for the personal `chief-of-staff` Hermes agent. The default deployment is
now **Podman Compose for the Hermes Gateway** while BlueBubbles itself remains a
macOS app because iMessage requires Messages.app on the host. It is intentionally
secure-by-default:

- enabled only for `profile_env: personal`
- no public tunnel is configured
- BlueBubbles open access is refused unless explicitly acknowledged
- BlueBubbles Server app install can be scripted from a pinned GitHub DMG with
  SHA256 verification, avoiding reliance on the deprecated Homebrew cask
- the BlueBubbles password is written only to a machine-local `0600` env file
- launchd service activation is opt-in after manual BlueBubbles setup works

Prerequisites outside Ansible:

1. Sign into Messages.app on the Mac and verify iMessage send/receive.
2. Install/configure BlueBubbles Server and note its local/Tailscale URL + password.
3. Prefer a local or Tailscale URL, e.g. `http://127.0.0.1:1234` when Hermes
   Gateway runs on the same Mac.

Recommended `ansible/inventory.local.yml` shape:

```yaml
profile_hosts:
  hosts:
    localhost:
      ansible_connection: local
      ansible_host: localhost
      profile_hermes_imessage_install_bluebubbles: true
      profile_hermes_imessage_bluebubbles_install_method: dmg
      profile_hermes_imessage_configure_gateway: true
      profile_hermes_imessage_deployment: podman_compose
      # Use host.containers.internal when BlueBubbles runs on the Mac host and
      # Hermes Gateway runs inside the Podman VM/container.
      profile_hermes_imessage_server_url: "http://host.containers.internal:1234"
      # Prefer 1Password/local secret reference when available:
      # profile_op_account: my.1password.com
      # profile_hermes_imessage_password_op_ref: "op://<vault>/<item>/bluebubbles_password"
      # Or, for local-only testing in ignored inventory.local.yml:
      # profile_hermes_imessage_password: "<BlueBubbles server password>"
      profile_hermes_imessage_allowed_users:
        - "+1YOURPHONE"
      profile_hermes_imessage_home_channel: "+1YOURPHONE"
      # Enable only after `hermes-cos-imessage-gateway` works manually:
      # profile_hermes_imessage_launchd_enabled: true
```

Run only this role:

```bash
TAGS=hermes_imessage just ansible-plan
PROFILE_ALLOW_HOST_MUTATION=1 TAGS=hermes_imessage just ansible-apply
```

Manual smoke test before launchd:

```bash
~/.local/bin/hermes-cos-imessage-compose build
~/.local/bin/hermes-cos-imessage-compose up
```

For host-native debugging only, the role also installs:

```bash
~/.local/bin/hermes-cos-imessage-gateway
```

Then text the iMessage account, approve DM pairing if prompted:

```bash
hermes pairing list
hermes pairing approve bluebubbles <CODE>
```

The role writes:

```text
~/.config/hermes-gateway/bluebubbles.env          # 0600, machine-local secret env
~/.config/hermes-gateway/imessage-compose/        # Containerfile + compose.yml
~/.local/bin/hermes-cos-imessage-compose          # Podman Compose launcher
~/.local/bin/hermes-cos-imessage-gateway          # host-native debug launcher
~/Library/LaunchAgents/com.karan.hermes-cos-imessage-gateway.plist  # only if launchd enabled
~/Library/Logs/hermes-gateway/imessage/           # stdout/stderr logs
```
