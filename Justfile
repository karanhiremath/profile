APPFILES := $(shell pwd)

all: install shell git fish tmux vim nvim python bash zsh starship

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
    # vim install
    touch $(HOME)/.netrc
    mkdir -p $(HOME)/.cache/nvim/undo
    mkdir -p $(HOME)/.config/nvim/


starship:
    # starship install
    ./bin/starship/install
