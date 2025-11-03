#!/bin/bash
# Main test runner for profile repository
# Tests installation across multiple OS environments using Docker

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROFILE_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# Source test config
. "${SCRIPT_DIR}/config.sh"

# Usage information
usage() {
    cat << EOF
Usage: $0 [OPTIONS] [OS...]

Test the profile repository installation across multiple OS environments.

OPTIONS:
    -h, --help          Show this help message
    -v, --verbose       Enable verbose output
    -k, --keep          Keep containers after tests
    -t, --timeout SEC   Set timeout for tests (default: 600)
    -a, --app APP       Test specific app (can be repeated)

OS VARIANTS (default: all):
    ubuntu              Test on Ubuntu 22.04
    debian              Test on Debian Bookworm
    rhel8               Test on RHEL 8
    nixos               Test on NixOS
    alpine              Test on Alpine Linux (experimental)
    all                 Test on all OS variants

EXAMPLES:
    $0 ubuntu           # Test on Ubuntu only
    $0 -v ubuntu rhel8  # Test on Ubuntu and RHEL8 with verbose output
    $0 -a tmux ubuntu   # Test only tmux installation on Ubuntu
    $0 --keep all       # Test all OS, keep containers

EOF
    exit 0
}

# Parse command line arguments
VERBOSE=0
KEEP_CONTAINERS=0
TIMEOUT=600
APPS_TO_TEST=""
OS_LIST=()

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            usage
            ;;
        -v|--verbose)
            VERBOSE=1
            shift
            ;;
        -k|--keep)
            KEEP_CONTAINERS=1
            shift
            ;;
        -t|--timeout)
            TIMEOUT="$2"
            shift 2
            ;;
        -a|--app)
            APPS_TO_TEST="$APPS_TO_TEST $2"
            shift 2
            ;;
        ubuntu|rhel8|nixos|alpine|debian|all)
            OS_LIST+=("$1")
            shift
            ;;
        *)
            log_error "Unknown option: $1"
            usage
            ;;
    esac
done

# Default to all OS if none specified
if [ ${#OS_LIST[@]} -eq 0 ]; then
    OS_LIST=("all")
fi

# Expand 'all' to all OS variants
if [[ " ${OS_LIST[@]} " =~ " all " ]]; then
    OS_LIST=(ubuntu debian rhel8 nixos alpine)
fi

# Export configuration
export TEST_VERBOSE=$VERBOSE
export TEST_KEEP_CONTAINERS=$KEEP_CONTAINERS
export TEST_TIMEOUT=$TIMEOUT
if [ -n "$APPS_TO_TEST" ]; then
    export APPS_TO_TEST
fi

log_info "Profile Test Runner"
log_info "==================="
log_info "Profile Directory: $PROFILE_DIR"
log_info "OS Variants: ${OS_LIST[*]}"
log_info "Timeout: ${TIMEOUT}s"
log_info "Keep Containers: $KEEP_CONTAINERS"
[ -n "$APPS_TO_TEST" ] && log_info "Apps to test: $APPS_TO_TEST"
echo

# Test results tracking
declare -A TEST_RESULTS

# Run tests for each OS
run_os_test() {
    local os=$1
    local dockerfile="${SCRIPT_DIR}/Dockerfile.${os}"
    local image_name="profile-test-${os}"
    local container_name="profile-test-${os}-$$"
    
    log_info "Testing on $os..."
    
    # Check if Dockerfile exists
    if [ ! -f "$dockerfile" ]; then
        log_error "Dockerfile not found: $dockerfile"
        TEST_RESULTS[$os]="SKIP"
        return 1
    fi
    
    # Build Docker image
    log_info "Building Docker image for $os..."
    if ! docker build -t "$image_name" -f "$dockerfile" "$PROFILE_DIR" 2>&1 | \
        ([ "$VERBOSE" -eq 1 ] && cat || grep -E "ERROR|error:|Step|Successfully" || true); then
        log_error "Failed to build Docker image for $os"
        TEST_RESULTS[$os]="BUILD_FAILED"
        return 1
    fi
    
    log_info "Docker image built successfully"
    
    # Run container and execute basic validation
    log_info "Running container for $os..."
    if ! docker run --name "$container_name" --rm "$image_name" \
        /bin/bash -c "
            export PROFILE_DIR=/home/testuser/profile
            export APP_BIN=/home/testuser/profile/bin
            cd /home/testuser/profile
            
            # Basic validation
            echo 'Checking environment...'
            echo \"PROFILE_DIR: \$PROFILE_DIR\"
            echo \"APP_BIN: \$APP_BIN\"
            
            # Check if bin/test/validate.sh exists
            if [ -f bin/test/validate.sh ]; then
                bash bin/test/validate.sh
            else
                echo 'Validation script not found, running basic checks...'
                command -v git && echo 'git: OK' || echo 'git: MISSING'
                command -v zsh && echo 'zsh: OK' || echo 'zsh: MISSING'
                command -v bash && echo 'bash: OK' || echo 'bash: MISSING'
            fi
        " 2>&1 | ([ "$VERBOSE" -eq 1 ] && cat || tail -20); then
        log_error "Container validation failed for $os"
        TEST_RESULTS[$os]="TEST_FAILED"
        return 1
    fi
    
    log_info "✓ Tests passed for $os"
    TEST_RESULTS[$os]="PASSED"
    return 0
}

# Main test execution
main() {
    local failed=0
    
    for os in "${OS_LIST[@]}"; do
        echo
        log_info "========================================"
        if run_os_test "$os"; then
            log_info "✓ $os: PASSED"
        else
            log_error "✗ $os: FAILED"
            ((failed++))
        fi
        log_info "========================================"
        echo
    done
    
    # Print summary
    echo
    log_info "Test Summary"
    log_info "============"
    for os in "${OS_LIST[@]}"; do
        result="${TEST_RESULTS[$os]:-UNKNOWN}"
        case $result in
            PASSED)
                echo -e "  ${COLOR_GREEN}✓${COLOR_RESET} $os: $result"
                ;;
            *)
                echo -e "  ${COLOR_RED}✗${COLOR_RESET} $os: $result"
                ;;
        esac
    done
    echo
    
    if [ $failed -gt 0 ]; then
        log_error "Tests failed on $failed OS variant(s)"
        return 1
    else
        log_info "All tests passed!"
        return 0
    fi
}

# Run main function
main
exit $?
