# pi wrapper: pre-launch update check (core harness + extensions) for new
# sessions. The wrapper itself is installed to ~/.pi/agent/bin/ by
# bin/pi/install or bin/zsh/install.
[ -r "$HOME/.pi/agent/bin/pi-update-wrapper.sh" ] && source "$HOME/.pi/agent/bin/pi-update-wrapper.sh"