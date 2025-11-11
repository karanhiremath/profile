#!/bin/bash
# App-specific validation tests
# Tests that installed apps are working correctly

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "${SCRIPT_DIR}/config.sh"

# App validation functions

validate_git() {
    log_info "Validating git..."
    validate_command_exists "git" || return 1
    
    # Check git version
    local git_version=$(git --version)
    log_info "Git version: $git_version"
    
    # Test basic git command
    if git config --list > /dev/null 2>&1; then
        log_info "✓ Git configuration accessible"
    else
        log_warn "Git configuration may have issues"
    fi
    
    return 0
}

validate_tmux() {
    log_info "Validating tmux..."
    validate_command_exists "tmux" || return 1
    
    # Check tmux version
    local tmux_version=$(tmux -V 2>&1)
    log_info "Tmux version: $tmux_version"
    
    # Check tmux config if exists
    if [ -f "$HOME/.tmux.conf" ]; then
        log_info "✓ Tmux configuration exists"
    else
        log_warn "Tmux configuration not found"
    fi
    
    return 0
}

validate_vim() {
    log_info "Validating vim..."
    validate_command_exists "vim" || return 1
    
    # Check vim version
    local vim_version=$(vim --version | head -1)
    log_info "Vim version: $vim_version"
    
    # Check vimrc
    if [ -f "$HOME/.vimrc" ]; then
        log_info "✓ Vim configuration exists"
    else
        log_warn "Vim configuration not found"
    fi
    
    return 0
}

validate_nvim() {
    log_info "Validating nvim..."
    validate_command_exists "nvim" || return 1
    
    # Check nvim version
    local nvim_version=$(nvim --version | head -1)
    log_info "Nvim version: $nvim_version"
    
    # Check nvim config directory
    if [ -d "$HOME/.config/nvim" ]; then
        log_info "✓ Nvim configuration directory exists"
    else
        log_warn "Nvim configuration directory not found"
    fi
    
    return 0
}

validate_zsh() {
    log_info "Validating zsh..."
    validate_command_exists "zsh" || return 1
    
    # Check zsh version
    local zsh_version=$(zsh --version)
    log_info "Zsh version: $zsh_version"
    
    # Check zshrc
    if [ -f "$HOME/.zshrc" ]; then
        log_info "✓ Zsh configuration exists"
    else
        log_warn "Zsh configuration not found"
    fi
    
    return 0
}

validate_bash() {
    log_info "Validating bash..."
    validate_command_exists "bash" || return 1
    
    # Check bash version
    local bash_version=$(bash --version | head -1)
    log_info "Bash version: $bash_version"
    
    # Check bash profile
    if [ -f "$HOME/.bash_profile" ] || [ -f "$HOME/.bashrc" ]; then
        log_info "✓ Bash configuration exists"
    else
        log_warn "Bash configuration not found"
    fi
    
    return 0
}

validate_cargo() {
    log_info "Validating cargo..."
    validate_command_exists "cargo" || return 1
    
    # Check cargo version
    local cargo_version=$(cargo --version)
    log_info "Cargo version: $cargo_version"
    
    # Check cargo home
    if [ -d "$HOME/.cargo" ]; then
        log_info "✓ Cargo home directory exists"
    else
        log_warn "Cargo home directory not found"
    fi
    
    return 0
}

validate_just() {
    log_info "Validating just..."
    validate_command_exists "just" || return 1
    
    # Check just version
    local just_version=$(just --version)
    log_info "Just version: $just_version"
    
    return 0
}

# Source the common validation functions
validate_command_exists() {
    local cmd="$1"
    if command -v "$cmd" >/dev/null 2>&1; then
        log_info "✓ $cmd is installed"
        return 0
    else
        log_error "✗ $cmd is NOT installed"
        return 1
    fi
}

# Main validation dispatcher
validate_app() {
    local app="$1"
    case "$app" in
        git)    validate_git ;;
        tmux)   validate_tmux ;;
        vim)    validate_vim ;;
        nvim)   validate_nvim ;;
        zsh)    validate_zsh ;;
        bash)   validate_bash ;;
        cargo)  validate_cargo ;;
        just)   validate_just ;;
        *)
            log_warn "No specific validation for: $app"
            validate_command_exists "$app"
            ;;
    esac
}

# Run validation if script is executed directly
if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
    if [ $# -eq 0 ]; then
        log_error "Usage: $0 <app1> [app2] [app3] ..."
        exit 1
    fi
    
    failed=0
    for app in "$@"; do
        echo
        if validate_app "$app"; then
            log_info "✓ Validation passed for $app"
        else
            log_error "✗ Validation failed for $app"
            ((failed++))
        fi
    done
    
    echo
    if [ $failed -gt 0 ]; then
        log_error "Validation failed for $failed app(s)"
        exit 1
    else
        log_info "All validations passed!"
        exit 0
    fi
fi
