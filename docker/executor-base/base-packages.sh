#!/bin/bash
# 共通パッケージインストールスクリプト
# すべての言語環境で必要な基本ツールをインストールします

set -e

# 基本パッケージのインストール
apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    wget \
    jq \
    tree \
    ca-certificates \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# 作業ディレクトリの作成
mkdir -p /workspace/project /workspace/tmp

echo "Base packages installation completed."
