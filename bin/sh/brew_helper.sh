#!/bin/bash
# Helper function to ensure Homebrew is available in PATH
# Usage: source this file, then call ensure_brew_in_path

ensure_brew_in_path() {
    # Check if brew is already in PATH
    if command -v brew >/dev/null 2>&1; then
        return 0
    fi
    
    # Try to find and source brew
    if [ -f /opt/homebrew/bin/brew ]; then
        export PATH="/opt/homebrew/bin:$PATH"
        eval "$(/opt/homebrew/bin/brew shellenv)"
        return 0
    elif [ -f /usr/local/bin/brew ]; then
        export PATH="/usr/local/bin:$PATH"
        eval "$(/usr/local/bin/brew shellenv)"
        return 0
    elif [ -f /home/linuxbrew/.linuxbrew/bin/brew ]; then
        export PATH="/home/linuxbrew/.linuxbrew/bin:$PATH"
        eval "$(/home/linuxbrew/.linuxbrew/bin/brew shellenv)"
        return 0
    fi
    
    # Brew not found
    return 1
}

# Auto-source brew if on Mac/Linux and brew exists
if [[ "$(uname -s)" == "Darwin" ]] || [[ "$(uname -s)" == "Linux" ]]; then
    ensure_brew_in_path 2>/dev/null || true
fi
