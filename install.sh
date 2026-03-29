#!/bin/bash

set -euo pipefail

shopt -s failglob

export PROFILE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export APP_BIN="${PROFILE_DIR}/bin"

. "${APP_BIN}/sh/shell_fns" --source-only

generate_config_vars

echo "Machine: ${MACHINE} | Arch: ${ARCH}"
echo "Profile: ${PROFILE_DIR}"
echo ""

# --- Shell setup ---

# Ensure .zshrc exists
touch ~/.zshrc

# Source shell profiles
for profile_file in zsh_profile.sh myprofile.sh; do
    if grep -q "${PROFILE_DIR}/${profile_file}" ~/.zshrc 2>/dev/null; then
        echo "✓ ${profile_file} already sourced in ~/.zshrc"
    else
        echo "Adding ${profile_file} to ~/.zshrc"
        echo "source ${PROFILE_DIR}/${profile_file}" >> ~/.zshrc
    fi
done

# Ensure ~/.local/bin is in PATH via .zshrc
if grep -q '\.local/bin' ~/.zshrc 2>/dev/null; then
    echo "✓ ~/.local/bin already in PATH"
else
    echo 'export PATH="${HOME}/.local/bin:${PATH}"' >> ~/.zshrc
    echo "Added ~/.local/bin to PATH in ~/.zshrc"
fi

# --- Prerequisites ---

# Install cargo (needed for bob-nvim)
install_app "cargo"
. "$HOME/.cargo/env"

# Install just (task runner)
install_app "just"

# On Mac, install brew early
if [[ "${MACHINE}" == "Mac" ]]; then
    echo ""
    echo "Installing Homebrew..."
    install_app "brew"

    # Ensure brew is in PATH
    if [ -f /opt/homebrew/bin/brew ]; then
        export PATH="/opt/homebrew/bin:$PATH"
        eval "$(/opt/homebrew/bin/brew shellenv)"
    elif [ -f /usr/local/bin/brew ]; then
        export PATH="/usr/local/bin:$PATH"
        eval "$(/usr/local/bin/brew shellenv)"
    fi

    # Add brew to .zshrc if not present
    if ! grep -q "/opt/homebrew/bin" ~/.zshrc 2>/dev/null; then
        echo 'export PATH="/opt/homebrew/bin:$PATH"' >> ~/.zshrc
        echo "Added Homebrew to PATH in ~/.zshrc"
    fi
fi

# --- Core tools ---

echo ""
echo "Installing core tools..."
just git
just tmux
just nvim

# --- Platform-specific ---

if [[ "${MACHINE}" == "Mac" ]]; then
    echo ""
    echo "Running Mac-specific setup..."
    just mac
fi

# --- tmux plugin manager ---

if [[ ! -d ~/.tmux/plugins/tpm ]]; then
    echo "Installing tmux plugin manager..."
    git clone https://github.com/tmux-plugins/tpm ~/.tmux/plugins/tpm
else
    echo "✓ tmux plugin manager already installed"
fi

echo ""
echo "✓ Profile installation complete"
echo "  Run 'source ~/.zshrc' or start a new shell to activate"
