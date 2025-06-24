#!/bin/zsh

# .envをexport付きで読み込む
if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

conda run -n coding-agent python -u main.py
