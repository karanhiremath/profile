# Profile Testing Infrastructure

This directory contains container-based testing infrastructure for validating the profile repository installation across multiple operating systems using Podman or Docker.

## Overview

The testing framework spins up containers with different OS variants and validates that the profile repository installs correctly and that each app is handled properly. The framework automatically detects and prefers Podman over Docker for improved security and rootless operation.

## Container Engine

The test infrastructure supports both **Podman** (preferred) and **Docker**:

- **Podman** (recommended): Daemonless, rootless container engine that's fully compatible with Docker
- **Docker**: Traditional container engine with daemon

The framework automatically detects which tool is available and uses Podman if both are installed.

## Supported Operating Systems

- **Ubuntu** (22.04): Debian-based Linux distribution
- **Debian** (Bookworm): Stable Debian release
- **RHEL 8**: Red Hat Enterprise Linux 8 (using UBI base image)
- **NixOS**: NixOS Linux distribution with Nix package manager
- **Alpine**: Lightweight Alpine Linux (experimental - may have package repo issues)

## Directory Structure

```
bin/test/
├── config.sh                  # Common configuration and helper functions
├── run-tests.sh              # Main test runner script
├── validate.sh               # Basic installation validation
├── validate-apps.sh          # App-specific validation tests
├── Dockerfile.ubuntu         # Ubuntu test environment
├── Dockerfile.debian         # Debian test environment
├── Dockerfile.rhel8          # RHEL 8 test environment
├── Dockerfile.nixos          # NixOS test environment
├── Dockerfile.alpine         # Alpine test environment
└── README.md                 # This file
```

## Usage

### Using Just Commands (Recommended)

The easiest way to run tests is using the `just` commands defined in the root Justfile:

```bash
# Test on all OS variants
just test

# Test on specific OS
just test-ubuntu
just test-debian
just test-rhel8
just test-nixos
just test-alpine

# Test specific app installation
just test-app tmux

# Run tests with verbose output
just test-verbose

# Validate apps are installed correctly (run inside container or after install)
just validate-apps git tmux vim
```

### Using the Test Runner Directly

You can also run the test runner script directly for more control:

```bash
# Test all OS variants
./bin/test/run-tests.sh all

# Test specific OS variants
./bin/test/run-tests.sh ubuntu rhel8

# Test with verbose output
./bin/test/run-tests.sh -v ubuntu

# Keep containers after tests (for debugging)
./bin/test/run-tests.sh -k ubuntu

# Test specific app
./bin/test/run-tests.sh -a tmux ubuntu

# Set custom timeout (in seconds)
./bin/test/run-tests.sh -t 900 all

# Get help
./bin/test/run-tests.sh --help
```

## Test Process

For each OS variant, the test framework:

1. **Builds Container Image**: Creates a container image with the OS and basic dependencies
2. **Copies Repository**: Copies the profile repository into the container
3. **Runs Validation**: Executes validation scripts to check:
   - Environment variables are set correctly
   - Basic commands are available (git, zsh, bash, etc.)
   - Configuration files are created properly
   - Apps can be executed

## Configuration

You can customize test behavior using environment variables:

```bash
# Force specific container engine (default: auto-detect, prefers podman)
export CONTAINER_ENGINE=podman  # or docker

# Set timeout for tests (default: 600 seconds)
export TEST_TIMEOUT=900

# Enable verbose output (default: 0)
export TEST_VERBOSE=1

# Keep containers after tests (default: 0)
export TEST_KEEP_CONTAINERS=1

# Specify apps to test (space-separated)
export APPS_TO_TEST="git tmux vim zsh"
```

## Validation Scripts

### validate.sh

Basic validation script that checks:
- Shell configuration files exist
- Common apps are installed
- PROFILE_DIR environment variable is set

### validate-apps.sh

App-specific validation that checks:
- App is installed and executable
- App version can be retrieved
- App configuration files exist
- App can execute basic commands

Supported apps:
- git
- tmux
- vim
- nvim
- zsh
- bash
- cargo
- just

## Custom Container Images

You can use custom container images by setting environment variables:

```bash
export UBUNTU_IMAGE="ubuntu:20.04"
export RHEL8_IMAGE="registry.access.redhat.com/ubi8/ubi:latest"
export NIXOS_IMAGE="nixos/nix:2.18.1"
```

Or create your own Dockerfile/Containerfile:

```dockerfile
FROM your-base-image:tag

# Install dependencies
RUN apt-get update && apt-get install -y curl git

# Create test user
RUN useradd -m -s /bin/bash testuser

USER testuser
WORKDIR /home/testuser

# Copy profile repository
COPY --chown=testuser:testuser . /home/testuser/profile

ENV PROFILE_DIR=/home/testuser/profile
ENV APP_BIN=/home/testuser/profile/bin

WORKDIR /home/testuser/profile
CMD ["/bin/bash"]
```

Save as `Dockerfile.custom` in this directory and run:

```bash
./bin/test/run-tests.sh custom
```

## Troubleshooting

### Build Failures

If container image build fails:
- Check that Podman or Docker is installed and running
- Verify network connectivity for package downloads
- Try building with verbose output: `-v` flag

### Container Engine Issues

If the wrong container engine is being used:
- Set explicitly: `export CONTAINER_ENGINE=podman`
- Check which is available: `command -v podman` or `command -v docker`

### Test Failures

If tests fail:
- Use `-v` flag for verbose output
- Use `-k` flag to keep containers for inspection
- Check logs: `$CONTAINER_ENGINE logs <container-name>`
- Enter the container: `$CONTAINER_ENGINE run -it <image-name> /bin/bash`

### Permission Issues

With Docker:
- Ensure Docker daemon is running
- Check that your user has Docker permissions
- Consider switching to Podman for rootless operation

With Podman:
- Rootless mode is default, no special permissions needed
- Ensure proper subuid/subgid mappings if issues occur

## Contributing

When adding new OS support:

1. Create a new Dockerfile: `Dockerfile.<os-name>`
2. Follow the existing Dockerfile structure
3. Update this README with the new OS
4. Test the new OS variant
5. Add corresponding `just` command if desired

## Examples

### Test Ubuntu Installation

```bash
# Quick test
just test-ubuntu

# Detailed test with verbose output
./bin/test/run-tests.sh -v ubuntu

# Test and keep container for inspection
./bin/test/run-tests.sh -k ubuntu
```

### Validate Specific Apps

```bash
# Inside a container or after local install
./bin/test/validate-apps.sh git tmux vim zsh

# Using just
just validate-apps git tmux vim
```

### Test Specific App Across All OS

```bash
# Test only tmux installation
just test-app tmux

# Or with test runner
./bin/test/run-tests.sh -a tmux all
```

## Notes

- Tests run in isolated Docker containers and don't affect your local system
- Each test creates a fresh container with a clean environment
- Containers are removed after tests unless `-k` flag is used
- Default timeout is 10 minutes per OS variant
- Mac-specific installations (Homebrew) are not tested in Docker containers
