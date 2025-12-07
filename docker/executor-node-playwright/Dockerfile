# Node.js + Playwright実行環境イメージ
# JavaScript/TypeScriptプロジェクト + Playwright用のDockerイメージ
FROM node:20-slim

# Gitユーザー設定用の引数
ARG BOT_NAME=bot
ARG BOT_EMAIL

# 共通パッケージとPlaywright依存ライブラリのインストール
# git: バージョン管理
# curl/wget: ファイルダウンロード
# jq: JSON処理
# tree: ディレクトリ構造表示
# Chromium依存ライブラリ: ブラウザ実行に必要
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    wget \
    jq \
    tree \
    ca-certificates \
    # Chromium依存ライブラリ
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    libatspi2.0-0 \
    # フォント
    fonts-liberation \
    fonts-noto-color-emoji \
    # その他
    xvfb \
    && rm -rf /var/lib/apt/lists/*

# Gitグローバル設定
RUN git config --global user.name "${BOT_NAME}" && \
    git config --global user.email "${BOT_EMAIL:-${BOT_NAME}@example.com}"

# Playwright本体とブラウザのインストール
RUN npm install -g playwright@1.49.0 && \
    npx playwright install chromium --with-deps

# Playwright MCP Serverのインストール
RUN npm install -g @executeautomation/playwright-mcp-server

# 作業ディレクトリの設定
WORKDIR /workspace

# プロジェクト配置用ディレクトリを作成
RUN mkdir -p /workspace/project

# スクリーンショット保存用ディレクトリを作成
RUN mkdir -p /workspace/project/screenshots

# Playwrightデータディレクトリを作成
RUN mkdir -p /workspace/.playwright

# コンテナを永続実行するためのENTRYPOINT
ENTRYPOINT ["sleep", "infinity"]
