#!/usr/bin/env bash

# .envをexport付きで読み込む
if [ -f config/.env ]; then
    set -a
    # shellcheck disable=SC1090
    source config/.env
    set +a
elif [ -f .env ]; then
    set -a
    # shellcheck disable=SC1090
    source .env
    set +a
fi

conda run -n coding-agent python -u main.py
