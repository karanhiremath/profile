#!/bin/bash
# Validation script to verify apps are installed correctly

set -euo pipefail

# Source test config
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "${SCRIPT_DIR}/config.sh"

# Validation functions
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

validate_file_exists() {
    local file="$1"
    if [ -f "$file" ]; then
        log_info "✓ File exists: $file"
        return 0
    else
        log_error "✗ File missing: $file"
        return 1
    fi
}

validate_directory_exists() {
    local dir="$1"
    if [ -d "$dir" ]; then
        log_info "✓ Directory exists: $dir"
        return 0
    else
        log_error "✗ Directory missing: $dir"
        return 1
    fi
}

validate_symlink() {
    local link="$1"
    if [ -L "$link" ]; then
        log_info "✓ Symlink exists: $link -> $(readlink "$link")"
        return 0
    else
        log_error "✗ Symlink missing: $link"
        return 1
    fi
}

# Main validation function
validate_installation() {
    local failed=0
    
    log_info "Starting installation validation..."
    
    # Check basic shell setup
    if validate_file_exists "$HOME/.zshrc"; then
        log_info "Shell configuration validated"
    else
        log_warn "Shell configuration may be incomplete"
    fi
    
    # Validate common apps
    for app in git zsh bash tmux; do
        if validate_command_exists "$app"; then
            log_info "$app validation passed"
        else
            log_error "$app validation failed"
            ((failed++))
        fi
    done
    
    # Check profile directory is set
    if [ -n "${PROFILE_DIR:-}" ]; then
        log_info "✓ PROFILE_DIR is set: $PROFILE_DIR"
    else
        log_warn "✗ PROFILE_DIR is not set"
        ((failed++))
    fi
    
    return $failed
}

# Run validation if script is executed directly
if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
    validate_installation
    exit $?
fi
