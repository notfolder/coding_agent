# Miniforge(conda)実行環境イメージ
# 科学計算・データサイエンスプロジェクトのDockerイメージ
FROM condaforge/miniforge3:latest

# Gitユーザー設定用の引数
ARG BOT_NAME=bot
ARG BOT_EMAIL

# 共通パッケージのインストール
# git: バージョン管理
# curl/wget: ファイルダウンロード
# jq: JSON処理
# tree: ディレクトリ構造表示
# nodejs/npm: text-editor MCPサーバー用
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    wget \
    jq \
    tree \
    ca-certificates \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Gitグローバル設定
RUN git config --global user.name "${BOT_NAME}" && \
    git config --global user.email "${BOT_EMAIL:-${BOT_NAME}@example.com}"

# Node.jsをインストール(text-editor MCP用)
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# 作業ディレクトリの設定
WORKDIR /workspace

# プロジェクト配置用ディレクトリを作成
RUN mkdir -p /workspace/project

# condaの初期設定
RUN conda init bash

# コンテナを永続実行するためのENTRYPOINT
ENTRYPOINT ["sleep", "infinity"]
