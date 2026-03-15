# Profile

Dotfiles and development environment setup, managed with [just](https://github.com/casey/just).

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
| `just mac` | Full macOS setup (brew, gh, tmux, ghostty, speedtest, rectangle, alfred, opentofu, steampipe) |
| `just alfred` | Alfred |
| `just iterm` | iTerm2 |
| `just raycast` | Raycast |

### AI Toolkit

Install everything with `just ai-toolkit`, or pick individual tools:

| Recipe | Description |
|--------|-------------|
| `just claude` | Claude Code |
| `just cmux` | cmux (Claude multiplexer) |
| `just copilot` | GitHub Copilot CLI |
| `just gemini-cli` | Gemini CLI |
| `just ollama` | Ollama |
| `just lmstudio` | LM Studio |
| `just huggingface` | Hugging Face CLI |
| `just vllm` | vLLM |

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
