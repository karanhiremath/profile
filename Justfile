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
    curl -O https://raw.githubusercontent.com/Homebrew/homebrew-cask/645973c9681519cfd471a4352f377cdd4e3f09b2/Casks/alfred.rb
    brew install --cask ./alfred.rb

git:
    # git install

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

mac:
    #!/usr/bin/env bash
    set -euo pipefail
    # Install brew first
    ./bin/brew/install
    # Source brew into PATH for Mac
    if [ -f /opt/homebrew/bin/brew ]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"
    elif [ -f /usr/local/bin/brew ]; then
        eval "$(/usr/local/bin/brew shellenv)"
    fi
    # Verify brew is available
    if ! command -v brew >/dev/null 2>&1; then
        echo "ERROR: Homebrew not found in PATH after installation."
        echo "Please run: eval \"\$(brew shellenv)\" or restart your shell"
        exit 1
    fi
    # Run Mac-specific installations
    just gh
    just tmux
    just ghostty
    brew tap teamookla/speedtest
    brew install speedtest --force
    brew install --cask rectangle
    just alfred
    just opentofu
    just steampipe

# Test commands
test:
    # Run tests on all OS variants
    ./bin/test/run-tests.sh all

test-ubuntu:
    # Test on Ubuntu
    ./bin/test/run-tests.sh ubuntu

test-debian:
    # Test on Debian
    ./bin/test/run-tests.sh debian

test-rhel8:
    # Test on RHEL 8
    ./bin/test/run-tests.sh rhel8

test-nixos:
    # Test on NixOS
    ./bin/test/run-tests.sh nixos

test-alpine:
    # Test on Alpine Linux
    ./bin/test/run-tests.sh alpine

test-app APP:
    # Test specific app installation
    ./bin/test/run-tests.sh -a {{APP}} all

test-verbose:
    # Run tests with verbose output
    ./bin/test/run-tests.sh -v all

validate-apps *APPS:
    # Validate that specific apps are installed correctly
    ./bin/test/validate-apps.sh {{APPS}}
