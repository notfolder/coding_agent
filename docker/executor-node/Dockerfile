# Node.js実行環境イメージ
# JavaScript/TypeScriptプロジェクト用のDockerイメージ
FROM node:20-slim

# Gitユーザー設定用の引数
ARG BOT_NAME=bot
ARG BOT_EMAIL

# 共通パッケージのインストール
# git: バージョン管理
# curl/wget: ファイルダウンロード
# jq: JSON処理
# tree: ディレクトリ構造表示
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    wget \
    jq \
    tree \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Gitグローバル設定
RUN git config --global user.name "${BOT_NAME}" && \
    git config --global user.email "${BOT_EMAIL:-${BOT_NAME}@example.com}"

# 作業ディレクトリの設定
WORKDIR /workspace

# プロジェクト配置用ディレクトリを作成
RUN mkdir -p /workspace/project

# コンテナを永続実行するためのENTRYPOINT
ENTRYPOINT ["sleep", "infinity"]
