# aos — portable platform binary

Self-updating host binary for Cos / CosW / fleet panes. Profile checkout still
owns launchers + YAML; this binary is what mini / tc2 / a sandbox can refresh
without a rust toolchain.

```
just aos                 # from-source install via mise rust / host cargo
just aos-update          # GitHub release when AOS_PIN_TAG or aos-v* exists
aos update --dry-run     # aos.update.v1 JSON
aos version
```

Never `curl | sh`. Transport is `gh release download` + SHA256SUMS (same
contract as `bin/omp/install`). Empty `pin.env` tag falls back to source.

## Layout

| Path | Role |
|---|---|
| `bin/aos` | checkout wrapper (`buf` / `vi` / `tty` / `update`) |
| `bin/aos-buf` | rust crate; bins `aos` + `aos-buf` |
| `bin/aos-buf/pin.env` | repo + tag + optional sha; copied to `~/.config/aos/pin.env` |
| `bin/aos-buf/devbox.json` | optional Jetify box (rustc/cargo/just/gh) |
| `.github/workflows/aos-release.yml` | tag `aos-v*` → multi-arch assets |

Host rust comes from mise (`rust` in `config/mise/config.toml`) or the
devbox. Toolkits (`just dev`) stay the CLI set; they do not replace `aos update`.

## Fleet-eng / Hermes

- **aos** = host platform (update, buf/apply, later data). Runs on the
  operator machine and inside sandboxes.
- **Hermes Cos / CosW** = fleet workers. YAML + `HERMES_HOME` stay in
  `~/src/hermes` (personal) or the work registry. Do not bake Cartesia
  facts into this crate.
- **fleet-eng** (when that repo exists) owns workflow DAG / lane policy.
  Workers call `aos update` / `aos buf`; they do not rsync dirty profile
  trees. After the first `aos-v*` release, vendor to mini/tc2 is
  `aos update` plus a fast-forward of `~/src/profile` for launchers.
- Many Cos panes per home; each pane is its own Hermes session. Never
  send-keys. Prompt writes go through `aos apply` / `atop vi`.

## Release

```
git tag aos-v0.1.0
git push origin aos-v0.1.0
# or Actions → aos-release → workflow_dispatch
```

Then set `AOS_PIN_TAG` / `AOS_PIN_SHA256` in `pin.env` for that host arch.
