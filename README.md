# Profile

A cross-platform development environment configuration repository with automated testing across multiple operating systems.

## Using this profile

### Automated Installation
1. Clone this repository wherever you want
2. Navigate to the repository
3. Run the following to start the install script
  
  ```bash
  ./install.sh
  ```

4. Reload your bash profile using
 
 ```bash
  source ~/.bash_profile
  ```

### Manual Installation

1. Clone this repository wherever you want
2. Add the following line to your `~/.bash_profile`
  
  ```bash
  source  [PATH TO REPO]/myprofile.sh
  ```

3. Add the following line to your `~/.vimrc`
  
  ```bash
  source [PATH TO REPO]/vimprofile.sh
  ```

4. Add the following line to your `~/.tmux.conf`

  ```bash
  source-file [PATH TO REPO]/tmuxprofile.conf
  ```

5. Reload your bash profile using
  
  ```bash
  source ~/.bash_profile
  ```

## Testing

This repository includes comprehensive container-based testing infrastructure to validate installations across multiple operating systems using Podman or Docker.

### Quick Start

```bash
# Test on all supported OS variants
./bin/test/run-tests.sh all

# Test on specific OS
./bin/test/run-tests.sh ubuntu
./bin/test/run-tests.sh debian

# Using just (if installed)
just test
just test-ubuntu
just test-debian
```

### Supported Operating Systems

- **Ubuntu 22.04** - Debian-based Linux distribution
- **Debian Bookworm** - Stable Debian release
- **RHEL 8** - Red Hat Enterprise Linux (using UBI base)
- **NixOS** - NixOS with Nix package manager
- **Alpine Linux** - Lightweight Linux (experimental)

### Test Commands

```bash
# Run all tests
./bin/test/run-tests.sh all

# Test specific OS
./bin/test/run-tests.sh ubuntu

# Test with verbose output
./bin/test/run-tests.sh -v ubuntu

# Keep containers for debugging
./bin/test/run-tests.sh -k ubuntu

# Test specific app installation
./bin/test/run-tests.sh -a tmux ubuntu

# Validate installed apps
./bin/test/validate-apps.sh git tmux vim
```

For detailed testing documentation, see [bin/test/README.md](bin/test/README.md).

## Requirements

- Podman or Docker (for testing, Podman preferred)
- Bash
- Git

