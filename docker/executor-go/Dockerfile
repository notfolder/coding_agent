# Go実行環境Dockerfile
# Go 1.22 + golangci-lint + gofmt
# 用途: Goプロジェクト、CLIツール開発、マイクロサービス

FROM golang:1.22-bookworm

# メタデータ
LABEL maintainer="coding-agent"
LABEL description="Go development environment for coding agent executor"
LABEL version="1.0"

# 環境変数設定
ENV GOPATH=/go
ENV PATH="${GOPATH}/bin:${PATH}"

# golangci-lintのバージョン
ARG GOLANGCI_LINT_VERSION=v1.62.2

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

# golangci-lintのインストール
RUN curl -sSfL https://raw.githubusercontent.com/golangci/golangci-lint/master/install.sh | \
    sh -s -- -b $(go env GOPATH)/bin ${GOLANGCI_LINT_VERSION}

# 作業ディレクトリの作成
RUN mkdir -p /workspace/project /workspace/tmp

WORKDIR /workspace

# コンテナを永続実行するためのコマンド
CMD ["sleep", "infinity"]
