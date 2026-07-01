#!/usr/bin/env just --justfile

APP_BIN := "$(pwd)/bin"
HOME := "$(echo $HOME)"


# Install core tools
all: git tmux nvim pc

install:
    ./install.sh

# Install Ansible dependencies without mutating profile state
ansible-bootstrap:
    #!/usr/bin/env bash
    set -euo pipefail
    if ! command -v ansible-playbook >/dev/null 2>&1; then
        if command -v uv >/dev/null 2>&1; then
            uv tool install --with ansible ansible-core
        elif command -v brew >/dev/null 2>&1; then
            brew install ansible
        else
            echo "ansible-playbook not found; install Ansible with uv or the OS package manager first" >&2
            exit 1
        fi
    fi
    ansible-galaxy collection install -r ansible/requirements.yml

# Preview Ansible-managed workstation changes; safe default
ansible-plan:
    #!/usr/bin/env bash
    set -euo pipefail
    inventory="${ANSIBLE_INVENTORY:-ansible/inventory.local.yml}"
    if [ ! -f "$inventory" ]; then inventory="ansible/inventory.example.yml"; fi
    args=(ansible-playbook -i "$inventory" ansible/site.yml --check --diff --limit "${ANSIBLE_LIMIT:-localhost}" -e "profile_env=${PROFILE_ENV:-personal}")
    if [ -n "${TAGS:-}" ]; then args+=(--tags "$TAGS"); fi
    if [ "${PROFILE_INSTALL_TOOLS:-0}" = "1" ]; then args+=(-e profile_install_tools=true -e "profile_tools=${TOOLS:-[]}"); fi
    "${args[@]}"

# Apply Ansible-managed workstation changes; requires explicit host mutation opt-in
ansible-apply:
    #!/usr/bin/env bash
    set -euo pipefail
    if [ "${PROFILE_ALLOW_HOST_MUTATION:-0}" != "1" ]; then
        echo "refusing host mutation; rerun with PROFILE_ALLOW_HOST_MUTATION=1" >&2
        exit 1
    fi
    inventory="${ANSIBLE_INVENTORY:-ansible/inventory.local.yml}"
    if [ ! -f "$inventory" ]; then inventory="ansible/inventory.example.yml"; fi
    args=(ansible-playbook -i "$inventory" ansible/site.yml --diff --limit "${ANSIBLE_LIMIT:-localhost}" -e "profile_env=${PROFILE_ENV:-personal}" -e profile_allow_host_mutation=true)
    if [ -n "${TAGS:-}" ]; then args+=(--tags "$TAGS"); fi
    if [ "${PROFILE_INSTALL_TOOLS:-0}" = "1" ]; then args+=(-e profile_install_tools=true -e "profile_tools=${TOOLS:-[]}"); fi
    "${args[@]}"

# Apply one Ansible tag set, e.g. `just ansible-apply-tags dotfiles`
ansible-apply-tags TAGS:
    TAGS="{{TAGS}}" just ansible-apply

# Build isolated control image for agent/dev workflows
agent-container-build:
    #!/usr/bin/env bash
    set -euo pipefail
    engine="${CONTAINER_ENGINE:-}"
    if [ -z "$engine" ]; then
        if command -v podman >/dev/null 2>&1; then engine=podman; elif command -v docker >/dev/null 2>&1; then engine=docker; else echo "podman/docker not found" >&2; exit 1; fi
    fi
    "$engine" build -f ansible/container/Containerfile -t profile-agent-ansible .

# Open an isolated repo shell: repo mounted, disposable HOME, no host credential mounts
agent-container-shell:
    #!/usr/bin/env bash
    set -euo pipefail
    engine="${CONTAINER_ENGINE:-}"
    if [ -z "$engine" ]; then
        if command -v podman >/dev/null 2>&1; then engine=podman; elif command -v docker >/dev/null 2>&1; then engine=docker; else echo "podman/docker not found" >&2; exit 1; fi
    fi
    mkdir -p .agent-home
    "$engine" run --rm -it \
        -v "$(pwd):/workspace/profile:rw" \
        -v "$(pwd)/.agent-home:/agent-home:rw" \
        -e HOME=/agent-home \
        --workdir /workspace/profile \
        --entrypoint bash \
        profile-agent-ansible

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
    # Install profile-managed Pi skills.
    if [ -d "$(pwd)/skills/pi" ]; then
        mkdir -p "$HOME/.pi/agent/skills"
        for skill in "$(pwd)"/skills/pi/*; do
            [ -d "$skill" ] || continue
            ln -fns "$skill" "$HOME/.pi/agent/skills/$(basename "$skill")"
        done
        echo "✓ Linked profile Pi skills"
    fi
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

# Personal agent-config sync (symlinks + pull-only cron). Safe on the work Mac.
agentic-sync:
    #!/usr/bin/env bash
    set -euo pipefail
    export PROFILE_DIR="$(pwd)"
    export APP_BIN="${PROFILE_DIR}/bin"
    ./bin/agentic-sync/install

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

# Install/upgrade pi coding agent + profile-managed theme
pi:
    #!/usr/bin/env bash
    set -euo pipefail
    export PROFILE_DIR="$(pwd)"
    export APP_BIN="${PROFILE_DIR}/bin"
    ./bin/pi/install

# Link profile-managed Pi skills into ~/.pi/agent/skills
pi-skills:
    #!/usr/bin/env bash
    set -euo pipefail
    mkdir -p "$HOME/.pi/agent/skills"
    for skill in "$(pwd)"/skills/pi/*; do
        [ -d "$skill" ] || continue
        ln -fns "$skill" "$HOME/.pi/agent/skills/$(basename "$skill")"
    done

# Link Codex.app CLI for shell/tmux use
codex:
    #!/usr/bin/env bash
    set -euo pipefail
    export PROFILE_DIR="$(pwd)"
    export APP_BIN="${PROFILE_DIR}/bin"
    ./bin/codex/install

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

# Bootstrap Cursor agents/skills + cli-config (day-to-day setup)
cursor-setup:
    #!/usr/bin/env bash
    set -euo pipefail
    export PROFILE_DIR="$(pwd)"
    export APP_BIN="${PROFILE_DIR}/bin"
    chmod +x ./bin/cursor-cli/setup
    ./bin/cursor-cli/setup

# Install/upgrade Devin for Terminal
devin:
    #!/usr/bin/env bash
    set -euo pipefail
    export PROFILE_DIR="$(pwd)"
    export APP_BIN="${PROFILE_DIR}/bin"
    ./bin/devin/install

# Install/upgrade Omnigent
omnigent:
    #!/usr/bin/env bash
    set -euo pipefail
    export PROFILE_DIR="$(pwd)"
    export APP_BIN="${PROFILE_DIR}/bin"
    ./bin/omnigent/install

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

# Install/upgrade herdr (agent multiplexer; runs inside tmux)
herdr:
    #!/usr/bin/env bash
    set -euo pipefail
    export PROFILE_DIR="$(pwd)"
    export APP_BIN="${PROFILE_DIR}/bin"
    ./bin/herdr/install

# Install/upgrade Hermes Agent + herm TUI wrappers
hermes:
    #!/usr/bin/env bash
    set -euo pipefail
    export PROFILE_DIR="$(pwd)"
    export APP_BIN="${PROFILE_DIR}/bin"
    ./bin/hermes/install

# Diagnose Hermes/herm/profile wrapper setup
hermes-doctor:
    #!/usr/bin/env bash
    set -euo pipefail
    export PROFILE_DIR="$(pwd)"
    export APP_BIN="${PROFILE_DIR}/bin"
    ./bin/hermes/doctor

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

# Install/upgrade AltTab (macOS window switcher)
alt-tab:
    #!/usr/bin/env bash
    set -euo pipefail
    export PROFILE_DIR="$(pwd)"
    export APP_BIN="${PROFILE_DIR}/bin"
    ./bin/alt-tab/install

# Install/upgrade DockDoor (macOS window peeking utility)
dockdoor:
    #!/usr/bin/env bash
    set -euo pipefail
    export PROFILE_DIR="$(pwd)"
    export APP_BIN="${PROFILE_DIR}/bin"
    ./bin/dockdoor/install

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
    just alt-tab
    just dockdoor
    just raycast
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
