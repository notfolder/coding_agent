# Miniforge実行環境Dockerfile
# conda/mamba + Python + データサイエンスツール
# 用途: 科学計算、データサイエンス、ML/AIプロジェクト

FROM condaforge/miniforge3:latest

# メタデータ
LABEL maintainer="coding-agent"
LABEL description="Data science environment with conda/mamba for coding agent executor"
LABEL version="1.0"

# 環境変数設定
ENV PYTHONUNBUFFERED=1

# 基本パッケージのインストール（apt）
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    wget \
    jq \
    tree \
    ca-certificates \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# condaの初期化とmambaによる基本ツールのインストール
RUN mamba install -y -c conda-forge \
    pytest \
    pytest-cov \
    black \
    flake8 \
    isort \
    && mamba clean -afy

# 作業ディレクトリの作成
RUN mkdir -p /workspace/project /workspace/tmp

WORKDIR /workspace

# コンテナを永続実行するためのコマンド
CMD ["sleep", "infinity"]
