# Test Automation for Coding Agent

This directory contains comprehensive test automation for the coding agent project, implementing the requirements from issue #17.

## Overview

The test automation framework provides:

1. **Mock MCP Servers** - Simulates GitHub and GitLab MCP server interactions
2. **Mock LLM Client** - Provides configurable LLM responses for testing
3. **Unit Tests** - Tests individual components (TaskGetter, TaskHandler, etc.)
4. **Integration Tests** - Tests complete workflows end-to-end
5. **Test Configuration** - Mock-enabled configuration for testing

## Test Structure

```
tests/
├── __init__.py
├── test_config.yaml          # Test configuration with mock providers
├── run_tests.py              # Test runner script
├── mocks/                    # Mock implementations
│   ├── __init__.py
│   ├── mock_mcp_client.py    # Mock MCP server for GitHub/GitLab
│   └── mock_llm_client.py    # Mock LLM client with configurable responses
├── unit/                     # Unit tests
│   ├── test_github_tasks.py  # GitHub task management tests
│   ├── test_gitlab_tasks.py  # GitLab task management tests
│   └── test_task_handler.py  # Task processing and LLM interaction tests
└── integration/              # Integration tests
    └── test_workflow.py      # End-to-end workflow tests
```

## Key Features Tested

### GitHub Integration
- Issue discovery and filtering by labels
- Task state management (coding agent → processing → done)
- Issue commenting and updates
- Pull request handling

### GitLab Integration  
- Issue discovery and filtering by labels
- Task state management via labels
- Issue discussions and updates
- Merge request handling

### Task Processing
- LLM interaction with tool calls
- JSON response parsing and error handling
- Task queue operations
- Workflow state transitions

### Error Handling
- Invalid JSON response handling
- Tool call failures
- Network/API error simulation
- Recovery mechanisms

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
python3 -m unittest tests.unit.test_task_handler
python3 -m unittest tests.integration.test_workflow
```

## Mock Components

### Mock MCP Client (`MockMCPToolClient`)
- Simulates GitHub and GitLab MCP server responses
- Provides realistic mock data for issues, comments, labels
- Supports all required MCP tools (search_issues, get_issue, update_issue, etc.)
- Handles both GitHub and GitLab API patterns

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
  
mcp_servers:
  - mcp_server_name: "github"
    command: ["mock_github_server"]  # Mock GitHub MCP server
  - mcp_server_name: "gitlab" 
    command: ["mock_gitlab_server"]  # Mock GitLab MCP server
```

## Test Coverage

The tests cover the main requirements from the original issue:

1. ✅ **GitHub/GitLab Integration**: Tests issue/PR/MR retrieval and state management
2. ✅ **Mock LLM Usage**: Verifies MCP server interaction with mock LLMs  
3. ✅ **State Management**: Tests label transitions (coding agent → processing → done)
4. ✅ **Error Handling**: Tests recovery from JSON parsing and tool call errors
5. ✅ **Workflow Automation**: End-to-end tests of the complete coding agent workflow

## Benefits

- **No External Dependencies**: Tests run without requiring actual GitHub/GitLab tokens or LLM API access
- **Fast Execution**: Mock components enable rapid test execution
- **Reliable**: Tests are deterministic and don't depend on external service availability
- **Comprehensive**: Covers both happy path and error scenarios
- **Maintainable**: Well-structured with clear separation of concerns

## Future Enhancements

- Add performance testing for high-volume task processing
- Implement more sophisticated error scenarios
- Add tests for additional MCP server integrations
- Include load testing for concurrent task processing