# Real Integration Tests Setup

## Prerequisites

To run real integration tests with GitHub and GitLab APIs, you need:

### 1. Install MCP Dependencies

```bash
# Install Python MCP client
pip install mcp

# Install Node.js MCP servers
npm install @notfolder/github-mcp-server
npm install @zereight/mcp-gitlab
```

### 2. Environment Variables

#### GitHub Testing
```bash
export GITHUB_TOKEN="your_github_personal_access_token"
```

#### GitLab Testing  
```bash
export GITLAB_TOKEN="your_gitlab_personal_access_token"
export GITLAB_API_URL="https://gitlab.com/api/v4"  # Optional, defaults to gitlab.com
```

### 3. Test Repository Setup

#### GitHub
1. Create a test repository (e.g., `coding-agent-test`)
2. Create test issues with the label `coding agent`
3. Ensure your token has permissions for:
   - `repo` (full repository access)
   - `read:user` (read user profile)

#### GitLab
1. Create a test project (e.g., `coding-agent-test`)
2. Create test issues with the label `coding agent`
3. Ensure your token has scopes:
   - `api` (complete read/write API access)
   - `read_user` (read user profile)

## Running Tests

### With API Tokens (Real Integration Tests)
```bash
# Auto-detect and run real tests if tokens available
python3 -m tests.run_tests

# Force real integration tests
python3 -m tests.run_tests --real

# Real unit tests only
python3 -m tests.run_tests --unit

# Real integration tests only  
python3 -m tests.run_tests --integration
```

### Without API Tokens (Mock Tests)
```bash
# Run mock tests
python3 -m tests.run_tests --mock
```

### Interactive Demo
```bash
# Run interactive demo (requires API tokens)
python3 tests/demo.py
```

## Test Configuration

Test configurations are in:
- `tests/real_test_config_github.yaml` - GitHub real API configuration
- `tests/real_test_config_gitlab.yaml` - GitLab real API configuration
- `tests/test_config.yaml` - Mock test configuration

## Expected Test Results

When API tokens are available, the tests will:

1. **Connect to MCP Servers**: Verify GitHub/GitLab MCP server connectivity
2. **List Available Tools**: Show available MCP tools for each service
3. **Search/List Issues**: Find issues matching the configured criteria
4. **Test Task Creation**: Create task objects with real API data
5. **Test Workflows**: Execute complete task processing workflows
6. **Validate Data**: Ensure real API responses have expected structure

## Troubleshooting

### MCP Server Issues
```bash
# Test GitHub MCP server
npx @notfolder/github-mcp-server --version

# Test GitLab MCP server  
npx @zereight/mcp-gitlab --version
```

### Token Validation
```bash
# Test GitHub token
curl -H "Authorization: token $GITHUB_TOKEN" https://api.github.com/user

# Test GitLab token
curl -H "Authorization: Bearer $GITLAB_TOKEN" "$GITLAB_API_URL/user"
```

### Common Issues

1. **No issues found**: Create test issues with `coding agent` label
2. **Permission errors**: Ensure tokens have correct scopes
3. **Rate limits**: Use dedicated test repositories
4. **MCP server failures**: Check Node.js package installation