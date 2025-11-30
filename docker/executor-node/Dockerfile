# Node.js実行環境イメージ
# JavaScript/TypeScriptプロジェクト用のDockerイメージ
FROM node:20-slim

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

# 作業ディレクトリの設定
WORKDIR /workspace

# プロジェクト配置用ディレクトリを作成
RUN mkdir -p /workspace/project

# コンテナを永続実行するためのENTRYPOINT
ENTRYPOINT ["sleep", "infinity"]
