#!/usr/bin/env just --justfile

APP_BIN := "$(pwd)/bin"
HOME := "$(echo $HOME)"


# Install core tools
all: git tmux nvim pc

install:
    ./install.sh

# Bootstrap a personal node (profile + notes)
setup:
    #!/usr/bin/env bash
    set -euo pipefail
    SRC_DIR="${HOME}/src"
    mkdir -p "$SRC_DIR"
    echo "▸ profile already here"
    if [ -d "$SRC_DIR/notes/.git" ]; then
        echo "▸ notes — pulling"
        cd "$SRC_DIR/notes" && git pull --ff-only 2>/dev/null || true
    else
        echo "▸ cloning notes"
        git clone "https://github.com/karanhiremath/notes.git" "$SRC_DIR/notes"
    fi
    just install
    echo ""
    echo "Done. Repos:"
    echo "  ~/src/profile  (personal tooling)"
    echo "  ~/src/notes    (personal KB)"

alacritty:
    # alacritty install

alfred:
    #!/usr/bin/env bash
    set -euo pipefail
    export PROFILE_DIR="$(pwd)"
    export APP_BIN="${PROFILE_DIR}/bin"
    ./bin/alfred/install.sh

git:
    #!/usr/bin/env bash
    set -euo pipefail
    export PROFILE_DIR="$(pwd)"
    export APP_BIN="${PROFILE_DIR}/bin"
    ./bin/git/install

gh:
    #!/usr/bin/env bash
    set -euo pipefail
    export PROFILE_DIR="$(pwd)"
    export APP_BIN="${PROFILE_DIR}/bin"
    ./bin/gh/install

ghostty:
    #!/usr/bin/env bash
    set -euo pipefail
    export PROFILE_DIR="$(pwd)"
    export APP_BIN="${PROFILE_DIR}/bin"
    ./bin/ghostty/install
    ln -fns "${APP_BIN}"/ghostty/config "${HOME}"/.config/ghostty/config


tmux:
    #!/usr/bin/env bash
    set -euo pipefail
    export PROFILE_DIR="$(pwd)"
    export APP_BIN="${PROFILE_DIR}/bin"
    ./bin/tmux/install


nvim:
    #!/usr/bin/env bash
    set -euo pipefail
    export PROFILE_DIR="$(pwd)"
    export APP_BIN="${PROFILE_DIR}/bin"
    ./bin/nvim/install

# Build and install pc (pi-code session manager)
pc:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "Building pc..."
    cd bin/pc && cargo build --release
    mkdir -p "$HOME/.local/bin"
    cp target/release/pc "$HOME/.local/bin/pc"
    echo "✓ Installed pc to ~/.local/bin/pc"
    # Install Datadog MCP extension if DD env is set
    if [ -n "${DD_API_KEY:-}" ]; then
        mkdir -p "$HOME/.pi/agent/extensions"
        ln -fns "$(pwd)/extensions/datadog-mcp.ts" "$HOME/.pi/agent/extensions/datadog-mcp.ts"
        echo "✓ Linked Datadog MCP extension"
    fi

obsidian:
    #!/usr/bin/env bash
    set -euo pipefail
    export PROFILE_DIR="$(pwd)"
    export APP_BIN="${PROFILE_DIR}/bin"
    ./bin/obsidian/install

zsh:
    #!/usr/bin/env bash
    set -euo pipefail
    export PROFILE_DIR="$(pwd)"
    export APP_BIN="${PROFILE_DIR}/bin"
    ./bin/zsh/install

bash:
    #!/usr/bin/env bash
    set -euo pipefail
    export PROFILE_DIR="$(pwd)"
    export APP_BIN="${PROFILE_DIR}/bin"
    ./bin/bash/install

iterm:
    #!/usr/bin/env bash
    set -euo pipefail
    export PROFILE_DIR="$(pwd)"
    export APP_BIN="${PROFILE_DIR}/bin"
    ./bin/iterm/install

opentofu:
    #!/usr/bin/env bash
    set -euo pipefail
    export PROFILE_DIR="$(pwd)"
    export APP_BIN="${PROFILE_DIR}/bin"
    ./bin/opentofu/install

steampipe:
    #!/usr/bin/env bash
    set -euo pipefail
    export PROFILE_DIR="$(pwd)"
    export APP_BIN="${PROFILE_DIR}/bin"
    ./bin/steampipe/install

# Install/upgrade Ollama
ollama:
    #!/usr/bin/env bash
    set -euo pipefail
    export PROFILE_DIR="$(pwd)"
    export APP_BIN="${PROFILE_DIR}/bin"
    ./bin/ollama/install

# Install/upgrade LM Studio
lmstudio:
    #!/usr/bin/env bash
    set -euo pipefail
    export PROFILE_DIR="$(pwd)"
    export APP_BIN="${PROFILE_DIR}/bin"
    ./bin/lmstudio/install

# Install/upgrade Hugging Face CLI
huggingface:
    #!/usr/bin/env bash
    set -euo pipefail
    export PROFILE_DIR="$(pwd)"
    export APP_BIN="${PROFILE_DIR}/bin"
    ./bin/huggingface/install

# Install/upgrade Raycast
raycast:
    #!/usr/bin/env bash
    set -euo pipefail
    export PROFILE_DIR="$(pwd)"
    export APP_BIN="${PROFILE_DIR}/bin"
    ./bin/raycast/install

# Install/upgrade Claude Code
claude:
    #!/usr/bin/env bash
    set -euo pipefail
    export PROFILE_DIR="$(pwd)"
    export APP_BIN="${PROFILE_DIR}/bin"
    ./bin/claude/install

# Install/upgrade cmux (Claude multiplexer)
cmux:
    #!/usr/bin/env bash
    set -euo pipefail
    export PROFILE_DIR="$(pwd)"
    export APP_BIN="${PROFILE_DIR}/bin"
    ./bin/cmux/install

# Install/upgrade GitHub Copilot CLI (standalone)
copilot:
    #!/usr/bin/env bash
    set -euo pipefail
    export PROFILE_DIR="$(pwd)"
    export APP_BIN="${PROFILE_DIR}/bin"
    ./bin/copilot-cli/install

# Install/upgrade GitHub Copilot CLI (alias for copilot)
copilot-cli:
    #!/usr/bin/env bash
    set -euo pipefail
    export PROFILE_DIR="$(pwd)"
    export APP_BIN="${PROFILE_DIR}/bin"
    ./bin/copilot-cli/install

# Install/upgrade Cursor Agent CLI
cursor-cli:
    #!/usr/bin/env bash
    set -euo pipefail
    export PROFILE_DIR="$(pwd)"
    export APP_BIN="${PROFILE_DIR}/bin"
    ./bin/cursor-cli/install

# Install/upgrade Devin for Terminal
devin:
    #!/usr/bin/env bash
    set -euo pipefail
    export PROFILE_DIR="$(pwd)"
    export APP_BIN="${PROFILE_DIR}/bin"
    ./bin/devin/install

# Install/upgrade Gemini CLI
gemini-cli:
    #!/usr/bin/env bash
    set -euo pipefail
    export PROFILE_DIR="$(pwd)"
    export APP_BIN="${PROFILE_DIR}/bin"
    ./bin/gemini-cli/install

# Install/upgrade vLLM
vllm:
    #!/usr/bin/env bash
    set -euo pipefail
    export PROFILE_DIR="$(pwd)"
    export APP_BIN="${PROFILE_DIR}/bin"
    ./bin/vllm/install

# Install/upgrade kubectl
kubectl:
    #!/usr/bin/env bash
    set -euo pipefail
    export PROFILE_DIR="$(pwd)"
    export APP_BIN="${PROFILE_DIR}/bin"
    ./bin/kubectl/install

# Install/upgrade Helm
helm:
    #!/usr/bin/env bash
    set -euo pipefail
    export PROFILE_DIR="$(pwd)"
    export APP_BIN="${PROFILE_DIR}/bin"
    ./bin/helm/install

# Install/upgrade kubectx and kubens
kubectx:
    #!/usr/bin/env bash
    set -euo pipefail
    export PROFILE_DIR="$(pwd)"
    export APP_BIN="${PROFILE_DIR}/bin"
    ./bin/kubectx/install

# Install/upgrade k9s
k9s:
    #!/usr/bin/env bash
    set -euo pipefail
    export PROFILE_DIR="$(pwd)"
    export APP_BIN="${PROFILE_DIR}/bin"
    ./bin/k9s/install

# Install/upgrade stern
stern:
    #!/usr/bin/env bash
    set -euo pipefail
    export PROFILE_DIR="$(pwd)"
    export APP_BIN="${PROFILE_DIR}/bin"
    ./bin/stern/install

# Install/upgrade kind
kind:
    #!/usr/bin/env bash
    set -euo pipefail
    export PROFILE_DIR="$(pwd)"
    export APP_BIN="${PROFILE_DIR}/bin"
    ./bin/kind/install

# Install/upgrade kustomize (standalone)
kustomize:
    #!/usr/bin/env bash
    set -euo pipefail
    export PROFILE_DIR="$(pwd)"
    export APP_BIN="${PROFILE_DIR}/bin"
    ./bin/kustomize/install

# Install/upgrade micromamba
micromamba:
    #!/usr/bin/env bash
    set -euo pipefail
    export PROFILE_DIR="$(pwd)"
    export APP_BIN="${PROFILE_DIR}/bin"
    ./bin/micromamba/install

# Install/upgrade all Kubernetes toolkit tools (continues on failure)
k8s-toolkit:
    #!/usr/bin/env bash
    set -euo pipefail
    export PROFILE_DIR="$(pwd)"
    export APP_BIN="${PROFILE_DIR}/bin"
    ./bin/k8s-toolkit/install-all

# Install/upgrade OpenVPN
openvpn:
    #!/usr/bin/env bash
    set -euo pipefail
    export PROFILE_DIR="$(pwd)"
    export APP_BIN="${PROFILE_DIR}/bin"
    ./bin/openvpn/install

# Install/upgrade btop
btop:
    #!/usr/bin/env bash
    set -euo pipefail
    export PROFILE_DIR="$(pwd)"
    export APP_BIN="${PROFILE_DIR}/bin"
    ./bin/btop/install

# Install claude-usage CLI and local OTEL stack
claude-usage:
    #!/usr/bin/env bash
    set -euo pipefail
    export PROFILE_DIR="$(pwd)"
    export APP_BIN="${PROFILE_DIR}/bin"
    ./bin/claude-usage/install

# Install/upgrade all AI toolkit tools (continues on failure)
ai-toolkit:
    #!/usr/bin/env bash
    set -euo pipefail
    export PROFILE_DIR="$(pwd)"
    export APP_BIN="${PROFILE_DIR}/bin"
    ./bin/ai-toolkit/install-all

podman:
    # Install and configure podman for testing
    #!/usr/bin/env bash
    set -euo pipefail
    export PROFILE_DIR="$(pwd)"
    ./bin/test/install

mac:
    #!/usr/bin/env bash
    set -euo pipefail
    # Install brew first
    ./bin/brew/install
    
    # Determine and source Homebrew location
    if [ -f /opt/homebrew/bin/brew ]; then
        export PATH="/opt/homebrew/bin:$PATH"
        eval "$(/opt/homebrew/bin/brew shellenv)"
        BREW_CMD="/opt/homebrew/bin/brew"
    elif [ -f /usr/local/bin/brew ]; then
        export PATH="/usr/local/bin:$PATH"
        eval "$(/usr/local/bin/brew shellenv)"
        BREW_CMD="/usr/local/bin/brew"
    else
        echo "ERROR: Homebrew not found after installation."
        echo "Expected locations:"
        echo "  - /opt/homebrew/bin/brew (Apple Silicon)"
        echo "  - /usr/local/bin/brew (Intel Mac)"
        echo ""
        echo "Please install Homebrew manually or check installation logs."
        exit 1
    fi
    
    # Verify brew is available
    if ! command -v brew >/dev/null 2>&1; then
        echo "ERROR: Homebrew not found in PATH."
        echo "Trying to use ${BREW_CMD} directly..."
        alias brew="${BREW_CMD}"
    fi
    
    # Run Mac-specific installations
    just gh
    just tmux
    just ghostty
    ${BREW_CMD} tap teamookla/speedtest
    ${BREW_CMD} install speedtest --force
    ${BREW_CMD} install --cask rectangle
    just alfred
    just opentofu
    just steampipe

# Test commands
test: podman
    # Run tests on all OS variants
    ./bin/test/run-tests.sh all

test-ubuntu: podman
    # Test on Ubuntu
    ./bin/test/run-tests.sh ubuntu

test-debian: podman
    # Test on Debian
    ./bin/test/run-tests.sh debian

test-rhel8: podman
    # Test on RHEL 8
    ./bin/test/run-tests.sh rhel8

test-nixos: podman
    # Test on NixOS
    ./bin/test/run-tests.sh nixos

test-alpine: podman
    # Test on Alpine Linux
    ./bin/test/run-tests.sh alpine

test-app APP: podman
    # Test specific app installation
    ./bin/test/run-tests.sh -a {{APP}} all

test-verbose: podman
    # Run tests with verbose output
    ./bin/test/run-tests.sh -v all

validate-apps *APPS:
    # Validate that specific apps are installed correctly
    ./bin/test/validate-apps.sh {{APPS}}
