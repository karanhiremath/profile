# Profile

Dotfiles and development environment setup, managed with [just](https://github.com/casey/just).

## Direction

Ansible is the environment-aware control plane. Defaults are local-only, check-first, and explicit-mutation to limit blast radius. Agentic/dev workflows should run in containers or isolated worktrees by default; see [Containerized Agentic Workflows SOP](docs/containerized-agentic-workflows.md).

## Quick Start

```bash
git clone https://github.com/karanhiremath/profile.git
cd profile
./install.sh
```

This installs core tooling (zsh, vim/nvim, tmux, ghostty, cargo, just) and sources shell configs into `~/.zshrc`. On macOS it also installs Homebrew and runs the `mac` recipe.

After install, reload your shell:

```bash
source ~/.zshrc
```

## Hermes sandbox entrypoint

`hs` is the short Hermes Sandbox entrypoint for personal project agent sessions. It resolves the current repo, a project under `~/src`, or an explicit path, then launches a sandboxed `herdr` session with disposable `HOME` and isolated `HERMES_HOME`/`HERMES_PROFILE` state.

```bash
hs                 # sandbox current repo and launch herdr
hs hermes          # sandbox ~/src/hermes
hs --shell foo     # sandbox ~/src/foo, shell only
hs --clean foo     # recreate foo's disposable sandbox HOME
hs --container-shell foo  # container shell: repo + disposable HOME mounted only
```

The default local `hs` sandbox isolates Hermes/herdr state and HOME-relative files; it does not block absolute host paths. Use `hs --container-shell` for filesystem isolation. Build that image first with `just agent-container-build`.

## Available Recipes

Run `just --list` for descriptions. Individual tools can be installed/upgraded independently.

### Shell & Editor

| Recipe | Description |
|--------|-------------|
| `just install` | Run full install script |
| `just all` | Install shell, git, tmux, vim, nvim, bash, zsh |
| `just vim` | Vim config + symlinks |
| `just nvim` | Neovim install |
| `just git` | Git config |
| `just tmux` | Tmux install + config |
| `just gh` | GitHub CLI |
| `just ghostty` | Ghostty terminal |
| `just zsh` | Zsh setup |
| `just bash` | Bash setup |

### macOS

| Recipe | Description |
|--------|-------------|
| `just mac` | Full macOS setup (brew, gh, tmux, ghostty, speedtest, rectangle, AltTab, DockDoor, Raycast, opentofu, steampipe) |
| `just alt-tab` | AltTab |
| `just dockdoor` | DockDoor |
| `just alfred` | Alfred |
| `just iterm` | iTerm2 |
| `just raycast` | Raycast |

### AI Toolkit

Install everything with `just ai-toolkit`, or pick individual tools:

| Recipe | Description |
|--------|-------------|
| `just claude` | Claude Code |
| `just pi` | pi coding agent + profile-managed theme |
| `just pi-skills` | Link profile-managed Pi skills |
| `just codex` | Codex CLI from Codex.app |
| `just cmux` | cmux (Claude multiplexer) |
| `just copilot` | GitHub Copilot CLI |
| `just cursor-cli` | Cursor Agent CLI |
| `just cursor-setup` | Cursor agents/skills + CLI config |
| `just devin` | Devin for Terminal |
| `just gemini-cli` | Gemini CLI |
| `just herdr` | herdr (agent multiplexer; runs inside tmux) |
| `just hermes` | Hermes Agent + herm TUI wrappers |
| `just hermes-doctor` | Hermes/herm/profile wrapper diagnostics |
| `just ollama` | Ollama |
| `just lmstudio` | LM Studio |
| `just huggingface` | Hugging Face CLI |
| `just vllm` | vLLM |

### Ansible workstation control plane

```bash
just ansible-bootstrap
just ansible-plan
PROFILE_ALLOW_HOST_MUTATION=1 just ansible-apply
PROFILE_ALLOW_HOST_MUTATION=1 just ansible-apply-tags dotfiles
PROFILE_ALLOW_HOST_MUTATION=1 PROFILE_INSTALL_TOOLS=1 TOOLS='["git","tmux","nvim"]' just ansible-apply-tags cli_tools
```

### Kubernetes Toolkit

Install everything with `just k8s-toolkit`, or pick individual tools:

| Recipe | Description |
|--------|-------------|
| `just kubectl` | kubectl |
| `just helm` | Helm |
| `just kubectx` | kubectx + kubens |
| `just k9s` | k9s |
| `just stern` | stern (log tailing) |
| `just kind` | kind (local clusters) |
| `just kustomize` | kustomize |

### Infrastructure

| Recipe | Description |
|--------|-------------|
| `just opentofu` | OpenTofu |
| `just steampipe` | Steampipe |
| `just openvpn` | OpenVPN |
| `just obsidian` | Obsidian |
| `just btop` | btop (system monitor) |
| `just micromamba` | micromamba (conda package manager) |

## Testing

Container-based testing with Podman/Docker across multiple OS variants.

```bash
just test           # all OS variants
just test-ubuntu    # specific OS
just test-app tmux  # specific app
just test-verbose   # verbose output
```

Supported: Ubuntu 22.04, Debian Bookworm, RHEL 8, NixOS, Alpine Linux.

See [bin/test/README.md](bin/test/README.md) for details.

## Requirements

- Bash, Git
- Podman or Docker (for testing only)
