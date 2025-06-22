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

# Python依存パッケージのインストール
COPY condaenv.yaml /tmp/condaenv.yaml
RUN conda env create -f /tmp/condaenv.yaml
SHELL ["conda", "run", "-n", "coding-agent", "/bin/bash", "-c"]

# 作業ディレクトリ
WORKDIR /app

# コードコピー
COPY . /app

# Node.js, npm, npxインストール
RUN apt-get update && \
    apt-get install -y nodejs npm git && \
    npm install -g npx

RUN npm install @zereight/mcp-gitlab@latest

COPY --from=build /bin/github-mcp-server ./github-mcp-server.cmd

# npxで@zereight/mcp-gitlabを起動し、main.pyも起動
ENTRYPOINT ["conda", "run", "-n", "coding-agent", "python", "main.py"]
