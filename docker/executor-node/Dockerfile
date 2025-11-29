# Node.js実行環境Dockerfile
# Node.js 20 LTS + npm/yarn/pnpm + TypeScript + ESLint
# 用途: フロントエンド開発、Node.jsバックエンド、TypeScriptプロジェクト

FROM node:20-slim

# メタデータ
LABEL maintainer="coding-agent"
LABEL description="Node.js development environment for coding agent executor"
LABEL version="1.0"

# 環境変数設定
ENV NODE_ENV=development

# 基本パッケージのインストール
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    wget \
    jq \
    tree \
    ca-certificates \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# グローバルパッケージマネージャーと開発ツールのインストール
RUN npm install -g \
    yarn \
    pnpm \
    typescript \
    ts-node \
    eslint \
    prettier

# 作業ディレクトリの作成
RUN mkdir -p /workspace/project /workspace/tmp

WORKDIR /workspace

# コンテナを永続実行するためのコマンド
CMD ["sleep", "infinity"]
