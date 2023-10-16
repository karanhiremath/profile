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

fish:
    # fish install

tmux:
    # tmux install
    ./bin/tmux/install

vim:
    #!/bin/sh
    # vim install
    touch "{{HOME}}/.netrc"
    mkdir -p "{{HOME}}/.cache/nvim/undo"
    mkdir -p "{{HOME}}/.config/nvim/"
    ln -fns "{{APP_BIN}}"/vim "{{HOME}}"/.vim
    ln -fs "{{APP_BIN}}"/vim/.vimrc "{{HOME}}"/.vimrc
    ln -fns "{{APP_BIN}}"/nvim/init.lua "{{HOME}}"/.config/nvim/init.lua
    ln -fns "{{APP_BIN}}"/nvim/lua "{{HOME}}"/.config/nvim/lua

nvim:
    # nvim install
    ./bin/nvim/install

python:
    # python install

bash:
    # bash install

zsh:
    #zsh install

iterm:
    # iterm install

    brew install --cask iterm2
    # Pulling latest iterm2_shell_integration.zsh and iterm2_shell_integration.bash
    curl -l https://iterm2.com/shell_integration/zsh \
        -o {{APP_BIN}}/iterm/.iterm2_shell_integration.zsh
    curl -l https://iterm2.com/shell_integration/bash \
        -o {{APP_BIN}}/iterm/.iterm2_shell_integration.bash

[macos]
mac:
    ./bin/brew/install
    just gh
    just tmux
    # just iterm
    brew tap teamookla/speedtest
    brew install speedtest --force
    brew install --cask rectangle
    brew install 1password-cli
    just alfred
