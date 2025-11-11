#!/usr/bin/env just --justfile

APP_BIN := "$(pwd)/bin"
HOME := "$(echo $HOME)"


all: shell git fish tmux vim nvim python bash zsh

install:
    ./install.sh

shell:
    # shell install

alacritty:
    # alacritty install

alfred:
    # alfred install
    ./bin/alfred/install.sh

git:
    # git install
    ./bin/git/install

gh:
    # github cli install
    ./bin/gh/install

ghostty:
    # ghostty install
    ./bin/ghostty/install
    ln -fns "{{APP_BIN}}"/ghostty/config "{{HOME}}"/.config/ghostty/config

fish:
    # fish install

tmux:
    # tmux install
    ./bin/tmux/install

vim:
    # vim install
    touch "{{HOME}}/.netrc"
    mkdir -p "{{HOME}}/.cache/nvim/undo"
    mkdir -p "{{HOME}}/.config/nvim/"
    ln -fns "{{APP_BIN}}"/vim "{{HOME}}"/.vim
    ln -fs "{{APP_BIN}}"/vim/.vimrc "{{HOME}}"/.vimrc
    ln -fns "{{APP_BIN}}"/nvim/init.lua "{{HOME}}"/.config/nvim/init.lua
    ln -fns "{{APP_BIN}}"/nvim/lua "{{HOME}}"/.config/nvim/lua
    ln -fns "{{APP_BIN}}"/nvim/after "{{HOME}}"/.config/nvim/after

nvim:
    # nvim install

    ./bin/nvim/install

obsidian:
    ./bin/obsidian/install

python:
    # python install

bash:
    # bash install

zsh:
    #zsh install

iterm:
    # iterm install
    ./bin/iterm/install

opentofu:
    # opentofu install
    ./bin/opentofu/install

steampipe:
    # steampipe install
    ./bin/steampipe/install

ai-toolkit:
    # AI toolkit install (ollama, lmstudio, huggingface)
    ./bin/ollama/install
    ./bin/lmstudio/install
    ./bin/huggingface/install

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
