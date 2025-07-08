# Test Automation for Coding Agent

This directory contains test automation for the coding agent project, modified per user request to remove GitHub and GitLab mocking.

## Overview

The test automation framework provides:

1. **Mock LLM Client** - Provides configurable LLM responses for testing
2. **Basic MCP Client Mock** - Generic MCP client interface without service-specific data
3. **Unit Tests** - Tests basic functionality without external service dependencies
4. **Integration Tests** - Tests framework components working together
5. **Test Configuration** - Mock-enabled configuration for testing

## Test Structure

```
tests/
├── __init__.py
├── test_config.yaml          # Test configuration with mock providers
├── run_tests.py              # Test runner script
├── demo.py                   # Demo of testing framework
├── mocks/                    # Mock implementations
│   ├── __init__.py
│   ├── mock_mcp_client.py    # Generic MCP client mock (GitHub/GitLab specifics removed)
│   └── mock_llm_client.py    # Mock LLM client with configurable responses
├── unit/                     # Unit tests
│   ├── test_github_tasks.py  # Basic GitHub-related functionality tests (no API mocking)
│   └── test_gitlab_tasks.py  # Basic GitLab-related functionality tests (no API mocking)
└── integration/              # Integration tests
    └── test_workflow.py      # Basic framework integration tests
```

## Key Features Tested

### LLM Integration
- Mock LLM client with configurable responses
- JSON response parsing and error handling
- Multi-turn conversation simulation
- Error recovery testing

### Basic GitHub/GitLab Functionality (No Service Mocking)
- URL parsing and basic data structure handling
- Label manipulation
- Prompt formatting
- Basic validation without API calls

### Framework Integration
- Mock components working together
- Configuration loading
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