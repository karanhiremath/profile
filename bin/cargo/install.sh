#!/bin/bash

set -euo pipefail

shopt -s failglob

curl https://sh.rustup.rs -sSf | sh
