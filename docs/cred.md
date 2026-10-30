# cred — personal credential plane

`just cred [domain]` links `cred` and `credential-sync` into `~/.local/bin` and
writes `~/.config/cred/host` (`domain=personal` by default; never overwritten).

| Command | Effect |
|---|---|
| `cred status [--json] [--only …]` | Health of codex grants, pi oauth, gh, 1Password, ssh-agent, tmux env, backends. Exit 1 on any `fail`. |
| `cred doctor --fix [--probe]` | Aligns diverged codex grants (single-writer adopt), unsets leaked `CODEX_*` vars from the global tmux env; `--probe` makes one live call against the configured codex model. |
| `cred sync codex` | Write-through the newest codex grant to Codex CLI, pi, and Hermes. |
| `cred probe codex -m <model>…` | Entitlement check: `entitled` vs `not entitled for this account/plan` vs `auth rejected`. |
| `cred backends` | List registered backends. |

Output carries no credential values: identities reduce to email domain, plan,
and a 6-char account suffix; tokens to presence, expiry, and alignment.

## Agent launch path

Launchers (`cosw`, …) call `credential-sync --provider <p>` before seat spawn.
Routing order:

1. A `cred-backend.v1` backend whose `domain` matches the host domain and lists
   the provider → `<backend> materialize --provider <p> --targets <csv> --apply`.
2. Built-in legacy implementation (codex → `bin/hermes/codex_grant_sync.py adopt`).
3. Structured no-op.

## Backend contract: `cred-backend.v1`

Executables in `~/.config/cred/backends.d/`. The profile ships none; other auth
planes install their own adapter on the hosts they own.

```
<backend> describe
  -> {"schema":"cred-backend.v1","name":"…","domain":"personal|work","providers":["openai-codex",…]}
<backend> materialize --provider <p> --targets <csv> [--apply]
  -> exit 0 on success; stdout/stderr must never contain credential values
<backend> status --json            (optional)
```

Rules:

- `domain` must equal the host's `domain`; a mismatched backend is reported as
  `fail` by `cred status` and is never routed.
- A backend owns its own authorization model. If its plane designates a single
  steward that mints credentials, the adapter files a request to that steward
  and consumes the staged output rather than minting credentials itself.
- Dependency direction is one-way: adapters may call `cred`; the profile never
  calls a named backend.
