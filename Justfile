#!/usr/bin/env just --justfile

set export

APP_BIN := join(justfile_directory(), "bin")
HOME := env_var("HOME")
os := os()
arch := arch()

# setup python binary
python3_bin := "$(which python3)"
python3_version := "$($(which python3) --version)"

default:
    @just --list

all: shell git fish tmux vim nvim python bash zsh

install:
    ./install.sh

app_install app:
    # installing {{app}} using installion script @ {{APP_BIN / app / "install"}}
    {{APP_BIN / app / "install"}}

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
    ln -fns "{{APP_BIN}}"/vim "{{HOME}}"/.vim
    ln -fs "{{APP_BIN}}"/vim/.vimrc "{{HOME}}"/.vimrc
    ln -fns "{{APP_BIN}}"/nvim/init.lua "{{HOME}}"/.config/nvim/init.lua
    ln -fns "{{APP_BIN}}"/nvim/lua "{{HOME}}"/.config/nvim/lua

nvim:
    # nvim install
    ./bin/nvim/install

python:
    # python install
    echo "python3 available at {{python3_bin}} running version {{python3_version}}"

bash:
    # bash install

zsh:
    #zsh install


@_app_dir app:
    if {{path_exists(clean(APP_BIN / app))}}; then \
        echo '{{APP_BIN / app}} directory exists!'; \
    else \
        echo 'Creating {{APP_BIN / app}}' && mkdir -p {{APP_BIN / app}} ; \
    fi

init app: (_app_dir app)
    # installing {{app}} to {{APP_BIN / app}}
    cp -R {{justfile_directory()}}/templates/app/* {{APP_BIN / app}}
