# Test Automation Framework

This directory contains a comprehensive test automation framework for the coding agent project, including both real API integration tests and mock tests.

## Overview

The test framework provides two modes of operation:

1. **Real Integration Tests**: Use actual GitHub and GitLab APIs for comprehensive end-to-end testing
2. **Mock Tests**: Use mock implementations for rapid development and CI/CD pipelines

## Test Structure

```
tests/
├── unit/                    # Unit tests for individual components
│   ├── test_github_tasks.py # Real GitHub API integration tests
│   └── test_gitlab_tasks.py # Real GitLab API integration tests
├── integration/             # End-to-end workflow tests
│   └── test_workflow.py     # Real GitHub/GitLab workflow tests
├── mocks/                   # Mock implementations
│   ├── mock_llm_client.py   # Mock LLM client
│   └── mock_mcp_client.py   # Mock MCP client (simplified)
├── real_test_config_github.yaml  # GitHub real API test configuration
├── real_test_config_gitlab.yaml  # GitLab real API test configuration
├── test_config.yaml         # Mock test configuration
├── run_tests.py             # Enhanced test runner
├── demo.py                  # Interactive demonstration
└── README.md               # This file
```

## Real Integration Tests

### Prerequisites

For real integration tests, you need:

#### GitHub Tests
- GitHub personal access token with appropriate permissions
- Access to a test repository (default: `notfolder/coding-agent-test`)
- Environment variable: `GITHUB_TOKEN`

#### GitLab Tests  
- GitLab personal access token with appropriate permissions
- Access to a test project (default: `coding-agent-test`)
- Environment variables: `GITLAB_TOKEN`, `GITLAB_API_URL` (optional)

### Test Capabilities

#### GitHub Integration Tests
- **MCP Server Connection**: Tests GitHub MCP server connectivity and tool availability
- **Issue Search**: Real GitHub issue search using the search API
- **Issue Details**: Retrieving issue details, comments, and metadata
- **Task Processing**: End-to-end GitHub task workflow with real data
- **Label Management**: Testing label updates and state transitions
- **Error Handling**: Robust error handling for API failures

#### GitLab Integration Tests
- **MCP Server Connection**: Tests GitLab MCP server connectivity and tool availability
- **Issue Listing**: Real GitLab issue listing with filtering
- **Issue Details**: Retrieving issue details and discussions
- **Task Processing**: End-to-end GitLab task workflow with real data
- **Label Management**: Testing label updates and state transitions
- **Error Handling**: Robust error handling for API failures

### Running Tests

#### All Tests (Auto-detect mode)
```bash
# Automatically runs real tests if tokens available, otherwise mock tests
python3 -m tests.run_tests
```

#### Real Integration Tests Only
```bash
# Requires GITHUB_TOKEN and/or GITLAB_TOKEN
python3 -m tests.run_tests --real
```

#### Unit Tests Only  
```bash
python3 -m tests.run_tests --unit
```

#### Integration Tests Only
```bash
python3 -m tests.run_tests --integration
```

#### Mock Tests Only
```bash
python3 -m tests.run_tests --mock
```

### Environment Setup

#### GitHub Setup
```bash
export GITHUB_TOKEN="your_github_token_here"
# Optional: specify test repository
export GITHUB_TEST_REPO="owner/repo-name"
```

#### GitLab Setup
```bash
export GITLAB_TOKEN="your_gitlab_token_here"  
# Optional: specify GitLab instance
export GITLAB_API_URL="https://gitlab.com/api/v4"
# Optional: specify test project
export GITLAB_TEST_PROJECT="project-name"
```

## Configuration

### Real Test Configurations

#### GitHub Configuration (`real_test_config_github.yaml`)
- Configures real GitHub MCP server with authentication
- Specifies test repository and query parameters
- Uses mock LLM client to isolate GitHub API testing

#### GitLab Configuration (`real_test_config_gitlab.yaml`)
- Configures real GitLab MCP server with authentication
- Specifies test project and query parameters
- Uses mock LLM client to isolate GitLab API testing

### Test Repository Setup

#### For GitHub
1. Create a test repository (e.g., `coding-agent-test`)
2. Create test issues with the `coding agent` label
3. Ensure your token has permissions for:
   - Reading issues and comments
   - Updating issue labels
   - Creating comments

#### For GitLab
1. Create a test project (e.g., `coding-agent-test`)
2. Create test issues with the `coding agent` label
3. Ensure your token has permissions for:
   - Reading issues and discussions
   - Updating issue labels
   - Creating notes/comments

## Test Features

### Comprehensive Coverage
- **API Integration**: Tests real API calls and responses
- **Error Handling**: Tests error scenarios and recovery
- **Data Validation**: Validates real API response structures
- **Workflow Testing**: Tests complete task processing workflows
- **State Management**: Tests label transitions and issue states

### Safety Features
- **Non-destructive**: Tests are designed to minimize impact on repositories
- **Graceful Degradation**: Tests skip if API tokens are not available
- **Isolated Testing**: Uses designated test repositories/projects
- **Error Recovery**: Robust error handling prevents test failures from affecting repositories

### Performance Considerations
- **Efficient API Usage**: Minimizes API calls to respect rate limits
- **Batched Operations**: Groups related operations where possible
- **Caching**: Caches results where appropriate to reduce API load

## Test Results

Real integration tests provide:

1. **Connectivity Verification**: Confirms MCP servers can connect to APIs
2. **Tool Availability**: Verifies all required MCP tools are accessible
3. **Data Integrity**: Validates real API response structures
4. **Workflow Validation**: Confirms complete task processing workflows
5. **Error Resilience**: Tests error handling and recovery mechanisms

## Troubleshooting

### Common Issues

#### GitHub Token Issues
```bash
# Check token permissions
curl -H "Authorization: token $GITHUB_TOKEN" https://api.github.com/user
```

#### GitLab Token Issues
```bash
# Check token permissions  
curl -H "Authorization: Bearer $GITLAB_TOKEN" "$GITLAB_API_URL/user"
```

#### MCP Server Issues
- Ensure Node.js packages are installed: `npm install`
- Check MCP server availability: `npx @notfolder/github-mcp-server --version`

### Test Failures

#### No Issues Found
- Create test issues in your test repository/project
- Ensure issues have the correct labels (`coding agent`)
- Verify repository/project access permissions

#### API Rate Limits
- Use dedicated test repositories to minimize API usage
- Implement delays between test runs if needed
- Use mock tests for frequent testing

#### Permission Errors
- Verify token has required scopes/permissions
- Check repository/project access rights
- Ensure test repository/project exists and is accessible

## Mock Tests

For development and CI/CD environments where API tokens are not available:

```bash
python3 -m tests.run_tests --mock
```

Mock tests provide basic framework validation without external dependencies.

## Interactive Demo

For manual testing and exploration:

```bash
python3 tests/demo.py
```

The demo provides an interactive interface to test various components manually.
- Basic workflow validation
## Running Tests

### Run All Tests
```bash
python3 -m tests.run_tests
```

### Run Only Unit Tests
```bash
python3 -m tests.run_tests --unit
```

### Run Only Integration Tests
```bash
python3 -m tests.run_tests --integration
```

### Run Individual Test Files
```bash
python3 -m unittest tests.unit.test_github_tasks
python3 -m unittest tests.unit.test_gitlab_tasks
python3 -m unittest tests.integration.test_workflow
```

### Run Interactive Demo
```bash
python3 tests/demo.py
```

## Mock Components

### Mock MCP Client (`MockMCPToolClient`)
- Generic MCP client interface for testing
- No longer provides GitHub/GitLab specific data (removed per user request)
- Returns empty responses for tool calls
- Supports basic MCP lifecycle operations

### Mock LLM Client (`MockLLMClient`)
- Configurable response queue for testing different scenarios
- Support for tool calls and JSON responses
- Error simulation with `MockLLMClientWithErrors`
- Tracks system prompts, user messages, and interactions

## Test Configuration

The test configuration (`test_config.yaml`) uses mock providers:

```yaml
llm:
  provider: "mock"  # Uses MockLLMClient instead of real LLM
```

## Test Coverage

The tests cover basic framework functionality without external service dependencies:

1. ✅ **LLM Mocking**: Mock LLM client with configurable responses
2. ✅ **Basic MCP Interface**: Generic MCP client operations
3. ✅ **Framework Integration**: Components working together
4. ✅ **Error Handling**: JSON parsing and error recovery
5. ✅ **Configuration**: Test configuration loading and validation

## Benefits

- **No External Dependencies**: Tests run without requiring GitHub/GitLab tokens or LLM API access
- **Fast Execution**: Mock components enable rapid test execution
- **Reliable**: Tests are deterministic and don't depend on external service availability
- **Simplified**: Focused on core framework functionality without service-specific complexity
- **Maintainable**: Well-structured with clear separation of concerns

## Important Notes

- **GitHub and GitLab mocking has been removed** per user request
- Tests now focus on basic functionality and LLM interaction patterns
- No actual GitHub/GitLab API calls are mocked or simulated
- Framework tests validate component integration without service dependencies