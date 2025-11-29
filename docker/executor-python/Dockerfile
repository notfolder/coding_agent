# Python実行環境Dockerfile
# Python 3.11 + pip + 開発ツール（pytest, black, flake8, mypy）
# 用途: 純粋なPythonプロジェクト、Django/Flask等のWebフレームワーク

FROM python:3.11-slim-bookworm

# メタデータ
LABEL maintainer="coding-agent"
LABEL description="Python development environment for coding agent executor"
LABEL version="1.0"

# 環境変数設定
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PIP_NO_CACHE_DIR=1

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

# pipのアップグレードと開発ツールのインストール
RUN pip install --upgrade pip && \
    pip install \
    pytest \
    pytest-cov \
    black \
    flake8 \
    mypy \
    isort \
    pylint

# 作業ディレクトリの作成
RUN mkdir -p /workspace/project /workspace/tmp

WORKDIR /workspace

# コンテナを永続実行するためのコマンド
CMD ["sleep", "infinity"]
