# Buzz client SOP

[Buzz](https://github.com/block/buzz) is a Nostr-relay-backed workspace where humans and
agents share channels. This repo carries only the *client* side: the `buzz` binary, the `bz`
context wrapper, and this SOP. Relay deployments, channel maps, agent registries, and
per-tenant denylists live outside this repo.

## Principle: the relay is the boundary

A Buzz relay process is the security boundary — one database, one relay keypair, one
relay-global member roster, with `channel_id` as the only sub-relay locality. The
multi-tenant "community" model in upstream `docs/multi-tenant-relay.md` is a draft spec, not
shipped code. Consequences:

- Separate trust domains get **separate relays**, not separate channels.
- An identity is scoped to one relay. Never register the same keypair on two relays.
- Anything published is effectively unretractable once other members have synced it.

## Install

```
just buzz              # buzz + bz
just buzz --with-acp   # also buzz-acp (the @mention harness; only where one runs)
```

`buzz-cli` is not on crates.io and is not in the relay container image, so it is built from a
pinned revision of `block/buzz` (see `BUZZ_REV` in `bin/buzz/install`). Keep the client
revision close to the relay's image revision.

On a host without a Rust toolchain — or a shared host where installing one is unwelcome —
build in a throwaway container and copy the binary out:

```
docker run --rm -v "$PWD/out":/out -v "$PWD/cargo-home":/cargo \
  -e CARGO_HOME=/cargo --cpus 8 --memory 16g rust:1.93-bookworm \
  cargo install --git https://github.com/block/buzz --rev <rev> --locked --root /out buzz-cli
```

Debian bookworm's glibc is old enough to run on current Ubuntu LTS. Keep build artifacts off
NFS/quota-bound home directories.

## Contexts

Contexts name a relay and where that relay's key comes from. They are machine-local and
uncommitted, because relay hostnames and vault coordinates are environment data:

```
~/.config/buzz/contexts/<name>.env      # mode 0600
  BUZZ_RELAY_URL=http://<relay-host>:3000
  BUZZ_KEY_OP_REF=op://<vault>/<item-id>/password
  BUZZ_OP_ACCOUNT=<1password-account>       # optional
  BUZZ_KEY_CMD=<command printing the key>   # alternative to BUZZ_KEY_OP_REF
```

Prefer the item **UUID** over its title in `BUZZ_KEY_OP_REF` — titles change, ids don't.

Usage:

```
bz --list                    # contexts and their relays
bz --check <ctx>             # liveness + authentication, no writes
bz <ctx> channels list       # any buzz subcommand
bz <ctx> --shell             # subshell carrying the context
```

`bz` resolves the key into the child process only. Do not `export BUZZ_PRIVATE_KEY` in an
interactive shell or a dotfile: it leaks into every child process and every agent you launch
from that shell.

## Data-boundary preflight

`bz` scans content-bearing subcommands (`messages send`, `send-diff`, `edit`, `canvas set`,
`mem set/patch`, `social publish`, `channels create/topic/purpose`, `users set-*`) and rejects
the call with exit **65** before anything reaches the relay. Built-in patterns cover generic
operator-environment leaks only: `/Users/<name>`, `/home/<name>`, `~/src/`, `Google Drive`,
Mac machine names, agent scratch paths.

Tenant-specific patterns (customer names, internal hostnames, project codenames) go in
`~/.config/buzz/denylist` — one extended-regex per line, `#` comments allowed. That file is
machine-local by design; it must not be committed to a synced dotfiles repo.

`--no-preflight` exists for reviewed false positives. Do not put it in an agent's permission
allowlist.

## Agent usage

Agents get narrow allowlist entries, never a blanket `Bash(bz:*)`:

```
Bash(bz <ctx> messages send:*)
Bash(bz <ctx> messages send-diff:*)
Bash(bz <ctx> channels list:*)
Bash(bz <ctx> mem:*)
```

One keypair per agent, minted and registered on exactly one relay. `buzz-acp` defaults to
`--respond-to owner-only`, and an agent whose owner attestation has not resolved silently
drops every inbound event — check that first when an agent appears mute.

Exit codes worth branching on: `0` ok, `1` user error, `2` network, `3` auth, `5` write
conflict, `65` preflight rejection (from `bz`, not `buzz`).
