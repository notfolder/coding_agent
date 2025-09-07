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
