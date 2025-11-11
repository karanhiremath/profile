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
    
    # Check profile directory is set
    if [ -n "${PROFILE_DIR:-}" ]; then
        log_info "✓ PROFILE_DIR is set: $PROFILE_DIR"
        
        # Validate profile directory structure
        if validate_directory_exists "$PROFILE_DIR"; then
            log_info "✓ Profile directory exists"
        else
            log_error "✗ Profile directory missing"
            ((failed++))
        fi
        
        # Check key directories and files
        if validate_directory_exists "$PROFILE_DIR/bin"; then
            log_info "✓ bin directory exists"
        else
            log_error "✗ bin directory missing"
            ((failed++))
        fi
        
        if validate_file_exists "$PROFILE_DIR/Justfile"; then
            log_info "✓ Justfile exists"
        else
            log_warn "✗ Justfile missing"
        fi
        
        if validate_file_exists "$PROFILE_DIR/install.sh"; then
            log_info "✓ install.sh exists"
        else
            log_warn "✗ install.sh missing"
        fi
    else
        log_error "✗ PROFILE_DIR is not set"
        ((failed++))
    fi
    
    # Validate that basic commands exist (pre-installed in container)
    log_info "Checking available commands..."
    for app in git bash; do
        if validate_command_exists "$app"; then
            log_info "$app is available"
        else
            log_warn "$app is not available (optional)"
        fi
    done
    
    # Check for zsh (optional)
    if command -v zsh >/dev/null 2>&1; then
        validate_command_exists "zsh"
        log_info "zsh is available"
    else
        log_info "zsh not available (optional)"
    fi
    
    return $failed
}

# Run validation if script is executed directly
if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
    validate_installation
    exit $?
fi
