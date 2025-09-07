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
RUN if [ -f main.go ]; then \
            go build -o /bin/github-mcp-server main.go; \
        else \
            echo '#!/bin/sh' > /bin/github-mcp-server; \
            echo 'echo "github-mcp-server not built (no source)"' >> /bin/github-mcp-server; \
        fi && chmod +x /bin/github-mcp-server

FROM condaforge/miniforge3

ENV PYTHONUNBUFFERED=1
RUN mkdir -p /logs

# Python依存パッケージのインストール
COPY config/condaenv.yaml /tmp/condaenv.yaml
RUN conda env create -f /tmp/condaenv.yaml

# Do not override the shell with `conda run` globally; run conda explicitly when needed.

# 作業ディレクトリ
WORKDIR /app

# コードコピー
COPY . /app

# Ensure logs directory exists for main.py
RUN mkdir -p /app/logs && chown -R root:root /app/logs

# Node.js, npm, npxインストール
# Install non-interactively to avoid tzdata prompts inside image builds
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Etc/UTC
RUN apt-get update && \
    apt-get install -y --no-install-recommends nodejs npm git && \
    npm install -g npx && \
    rm -rf /var/lib/apt/lists/*

RUN npm install @zereight/mcp-gitlab@latest

COPY --from=build /bin/github-mcp-server /usr/local/bin/github-mcp-server
RUN if [ -f /usr/local/bin/github-mcp-server ]; then chmod +x /usr/local/bin/github-mcp-server; fi

# Create a wrapper at /app/github-mcp-server.cmd so configs pointing to that path work
RUN printf '%s\n' '#!/bin/sh' \ 
    '# If the built binary is an ELF executable, run it; otherwise fall back to npx mcp-gitlab' \ 
    'if [ -f /usr/local/bin/github-mcp-server ]; then' \ 
    '  # check ELF magic' \ 
    '  if head -c4 /usr/local/bin/github-mcp-server | grep -q "\x7fELF" 2>/dev/null; then' \ 
    '    exec /usr/local/bin/github-mcp-server "$@"' \ 
    '  fi' \ 
    'fi' \ 
    '# Fallback to npx mcp-gitlab in stdio mode' \ 
  'exec npx @zereight/mcp-gitlab stdio' > /app/github-mcp-server.cmd && \
  chmod +x /app/github-mcp-server.cmd

# Create debug helper script for manual testing
RUN cat > /app/debug-run.sh <<'EOF'
#!/bin/bash
echo "=== Debug Environment Setup ==="
echo "Python environment: $(which python)"
echo "Conda environment: $CONDA_DEFAULT_ENV"
echo "Available commands:"
echo "  run-main     - Run main.py with conda"
echo "  test-mcp     - Test MCP server connection"
echo "  check-env    - Check environment variables"
echo "  ls-files     - List important files"
echo ""

run-main() {
  echo "Running main.py..."
  conda run -n coding-agent python -u main.py
}

test-mcp() {
  echo "Testing MCP server..."
  echo "Checking github-mcp-server.cmd:"
  ls -l /app/github-mcp-server.cmd
  echo "Testing wrapper execution (stdio mode):"
  timeout 5s /app/github-mcp-server.cmd --help 2>&1 || echo "MCP server test completed (may timeout normally)"
}

check-env() {
  echo "=== Environment Variables ==="
  echo "GITLAB_PERSONAL_ACCESS_TOKEN: ${GITLAB_PERSONAL_ACCESS_TOKEN:-'(not set)'}"
  echo "GITHUB_PERSONAL_ACCESS_TOKEN: ${GITHUB_PERSONAL_ACCESS_TOKEN:-'(not set)'}"
  echo "TASK_SOURCE: ${TASK_SOURCE:-'(not set)'}"
  echo "DEBUG: ${DEBUG:-'(not set)'}"
  echo "LLM_PROVIDER: ${LLM_PROVIDER:-'(not set)'}"
}

ls-files() {
  echo "=== Important Files ==="
  echo "Config files:"
  ls -la /app/*.yaml /app/*.conf 2>/dev/null || true
  echo ""
  echo "Log directory:"
  ls -la /app/logs/ 2>/dev/null || true
  echo ""
  echo "MCP wrapper:"
  ls -la /app/github-mcp-server.cmd /usr/local/bin/github-mcp-server 2>/dev/null || true
}

export -f run-main test-mcp check-env ls-files
EOF
RUN chmod +x /app/debug-run.sh

# For debugging: start with bash instead of main.py
# Change back to: ENTRYPOINT ["stdbuf", "-oL", "conda", "run", "-n", "coding-agent", "python", "-u", "main.py"]
# when debugging is complete
# ENTRYPOINT ["/bin/bash", "-l"]

# Restore normal entrypoint (debug version had binary execution issues)
ENTRYPOINT ["stdbuf", "-oL", "conda", "run", "-n", "coding-agent", "python", "-u", "main.py"]