# pc

`pc` is a Rust CLI for opening a **project-centric tmux workspace** around `pi`.

It is intended to be the personal/local counterpart to `tc`:
- `tc` → cluster / host attachment
- `pc` → local coding workspace orchestration

Source lives in:
- `~/src/profile/bin/pc/`

Installed binary:
- `~/.local/bin/pc`

---

## Goals

`pc` should make the default flow feel natural:

1. `mac`
2. `pc`
3. pick a project
4. land in a structured tmux workspace with editor + agent + shell + dashboard

It should work both:
- **outside tmux**: create a dedicated `pi_<project>` session
- **inside tmux**: add project windows into the current session without disturbing the rest of the session

---

## Intended UX

### `pc`
Open the project picker and create or switch to a project workspace.

### `pc <project>`
Open a workspace for a specific project.

### `pc dashboard <project>` / `db <project>`
Jump directly to the dashboard for that project.

### `pc save` / `pc load`
Save and restore workspace state.

### `pc vendor`
Commit, push, and optionally pull the repo on remote hosts for simple gitops-style propagation.

---

## Workspace model

A project workspace currently aims to create two tmux windows.

### Coding window: `<project>`

Intended structure:

```text
┌──────────────┬─────────────────┐
│              │                 │
│    NVIM      │       PI        │
│              │                 │
├──────────────┤                 │
│    ZSH       │                 │
└──────────────┴─────────────────┘
```

Intended pane roles:
- pane `0` → `nvim` (starts with telescope project/session picker)
- pane `1` → `pi`
- pane `2` → `zsh`

### Dashboard window: `<project>-db`

Intended structure:

```text
┌───────────────────────────────────────┐
│                 BTOP                  │
├──────────────┬──────────────┬─────────┤
│     k9s      │    slurm     │ dd/otel │
└──────────────┴──────────────┴─────────┘
```

The dashboard is adaptive and may include:
- `btop`
- `k9s`
- slurm queue / node overview
- Datadog log tail / MCP-adjacent workflows
- OTEL / agent logs
- docker / podman overview
- `nvidia-smi`
- fallback shells

---

## Current state

### Working

- Rust crate with typed CLI via `clap`
- build + test pass
- project discovery from `~/src`
- name sanitization for tmux-safe targets
- save/load session JSON format
- telescope integration wiring exists in nvim config
- dashboard panel detection exists
- vendor workflow exists
- inside/outside tmux branching exists

### In progress

The main area under active iteration is **pane orchestration**.

What is already solid:
- tmux session detection
- project/window naming
- CLI shape
- picker flow
- save/load format
- dashboard detection

What is still being refined:
- deterministic startup of the exact commands in the exact panes
- stable render of the coding layout when created inside an existing tmux session
- first-class `db` workflow / dashboard jump behavior
- multi-window save/load

This means the **project plan is solid**, but the final pane-start mechanics are still being tightened.

---

## Commands

### Core

```bash
pc                  # pick a project
pc bifrost          # open bifrost workspace
pc bifrost -- -c    # launch pi with --continue
pc status           # show active sessions
pc list             # machine-readable project list
pc list --json      # JSON project list
pc kill             # kill a session
pc save             # save current session
pc load             # restore a saved session
pc vendor           # commit/push/vendor repo changes
```

### Planned / expected

```bash
db                  # jump to current project's dashboard
pc dashboard        # dashboard-oriented workflow
pc attach <project> # attach only, never create
pc doctor           # environment / setup diagnostics
```

---

## Shell integration

Current shell/profile integration is in `~/src/profile/myprofile.sh`.

Expected helpers:
- `pc` → main CLI
- `db` → dashboard jump helper (planned)

`tc` remains cluster-focused and comes from `karan.hiremath` shell extensions.

---

## Neovim integration

Nvim integration lives at:
- `bin/nvim/lua/kh/telescope-pc.lua`

Keymaps currently wired:
- `<leader>fp` → project picker
- `<leader>pt` → toggle pi pane
- `<leader>pz` → toggle zsh pane
- `<leader>ps` → send current file / visual selection to pi
- `<leader>pk` → restart pi
- `<leader>pc` → continue pi session
- `<leader>pr` → resume pi session

---

## Configuration

Environment variables:

| Variable | Default | Description |
|---|---|---|
| `PC_SRC_DIR` | `~/src` | Project root |
| `PC_SAVES_DIR` | `~/.config/pc/sessions` | Saved session directory |
| `PC_SPLIT_PCT` | `35` | Intended pi pane width |
| `PC_ZSH_SPLIT_PCT` | `25` | Intended zsh pane height |
| `PC_NVIM_CMD` | telescope-pc launcher | Nvim startup command |
| `PC_DB_TOP` | `btop` | Dashboard top command |
| `PC_VENDOR_HOSTS` | empty | Comma-separated vendor hosts |
| `PI_BIN` | auto-detect | Path to `pi` |
| `NVIM_BIN` | auto-detect | Path to `nvim` |
| `DD_API_KEY` | unset | Enables Datadog-related dashboard behavior |
| `DD_APP_KEY` | unset | Required with Datadog API key |

---

## Build / install

From the profile repo:

```bash
just pc
```

Manual:

```bash
cd ~/src/profile/bin/pc
cargo build --release
cp target/release/pc ~/.local/bin/pc
```

---

## Test status

Current local test state:
- `cargo build --release` → passes
- `cargo test` → passes (`16` tests)

The current tests mostly cover:
- naming / sanitization
- session JSON round-trip
- project discovery behavior
- CLI exit behavior

Still needed:
- end-to-end pane/orchestration tests
- dashboard-specific tests
- inside-tmux workflow tests
- multi-window save/load tests

---

## Datadog / work-node integration

`pc` includes a Datadog MCP-related extension source at:
- `bin/pc/extensions/datadog-mcp.ts`

Goal:
- let `pi` query logs / metrics / monitors on work nodes where Datadog credentials are present

Dashboard behavior should also become smarter on work nodes:
- show slurm / cluster overviews when available
- show Datadog / OTEL panels when available

---

## Design principles

- keep tmux usage compatible with the existing personal tmux workflow
- do **not** replace or heavily mutate the user’s normal tmux config
- prefer predictable names and explicit windows over hidden state
- be safe for project names like `karan.hiremath`
- use Rust for type safety and maintainability
- keep workflows scriptable
- make local developer ergonomics good enough to reuse across machines and hosts

---

## Known issues

As of this checkpoint:

1. coding/dashboard windows are created correctly, but pane command startup still needs refinement
2. the `db` first-class flow is planned, not finished
3. save/load is not yet aware of both coding + dashboard windows together
4. some config fields are still present while the layout implementation is mid-refactor

---

## Roadmap

Canonical roadmap / ticket list:
- `~/src/notes/03_tech/pc-roadmap.md`

That file tracks:
- architecture intent
- known bugs
- next steps
- future enhancements

---

## Developer notes

If you are iterating on `pc`, start with:

1. `cargo build --release`
2. `cargo test`
3. manual workflow test:
   - `mac`
   - `pc`
   - pick `scratchpad`
4. verify:
   - coding window exists
   - dashboard window exists
   - pane commands start in the right places
5. update `pc-roadmap.md`
6. commit profile + notes changes

The next most valuable engineering change is:
- replace fragile pane startup with a deterministic layout renderer using stable tmux targets and pane respawn semantics
