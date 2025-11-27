FROM golang:1.24.4-alpine AS build
ARG VERSION="dev"

# Set the working directory
WORKDIR /build

# コードコピー
COPY . /build

WORKDIR /build/github-mcp-server/cmd/github-mcp-server

# Install git
RUN --mount=type=cache,target=/var/cache/apk \
    apk add git

# Build the server
# go build automatically download required module dependencies to /go/pkg/mod
# RUN CGO_ENABLED=0 go build -ldflags="-s -w -X main.version=${VERSION} -X main.commit=$(git rev-parse HEAD) -X main.date=$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
#     -o /bin/github-mcp-server /build/github-mcp-server/cmd/github-mcp-server/main.go
RUN go build -o /bin/github-mcp-server main.go

FROM condaforge/miniforge3

ENV PYTHONUNBUFFERED=1
RUN mkdir -p /logs

# Python依存パッケージのインストール
COPY condaenv.yaml /tmp/condaenv.yaml
RUN conda env create -f /tmp/condaenv.yaml
SHELL ["conda", "run", "-n", "coding-agent", "/bin/bash", "-c"]

# 作業ディレクトリ
WORKDIR /app

# コードコピー
COPY . /app

# Node.js, npm, gitインストール
RUN apt-get update && \
    apt-get install -y nodejs npm git

# グローバルにmcp-gitlabをインストール
RUN npm install -g @zereight/mcp-gitlab@latest

# npxもグローバルにインストール（既存の場合は上書き）
RUN npm install -g npx --force

COPY --from=build /bin/github-mcp-server ./github-mcp-server.cmd

# conda環境でPythonスクリプトを実行するためのエントリーポイント
ENTRYPOINT ["conda", "run", "-n", "coding-agent", "--no-capture-output"]
