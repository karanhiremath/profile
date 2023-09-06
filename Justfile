#!/usr/bin/env just --justfile

APP_BIN := "$(pwd)/bin"
HOME := "$(echo $HOME)"

all: shell git fish tmux vim nvim python bash zsh

install:
    ./install.sh

shell:
    # shell install

git:
    # git install

fish:
    # fish install

tmux:
    # tmux install

vim:
    #!/bin/sh
    # vim install
    touch "{{HOME}}/.netrc"
    mkdir -p "{{HOME}}/.cache/nvim/undo"
    mkdir -p "{{HOME}}/.config/nvim/"
    ln -fs "{{APP_BIN}}/vim" "{{HOME}}/.vim"
    ln -fs "{{APP_BIN}}/vim/.vimrc" "{{HOME}}/.vimrc"
    ln -fs "{{APP_BIN}}/nvim/init.lua "{{HOME}}/.config/nvim/init.lua"
    ln -fns "{{APP_BIN}}/nvim/lua "{{HOME}}/.config/nvim/init.lua"



nvim:
    # nvim install
    ./bin/nvim/install

python:
    # python install

bash:
    # bash install

zsh:
    #zsh install

