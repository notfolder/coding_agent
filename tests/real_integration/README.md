# Real Integration Tests Documentation

This document explains how to set up and run the real integration tests for the coding agent that use actual GitHub/GitLab and LLM APIs.

## Overview

The real integration tests implement the three test scenarios described in issue #24:

1. **Issue-based operation**: Create an issue asking to create `hello_world.py` with main function outputting "hello world"
2. **Issue-based pull request creation**: Create an issue asking to modify `hello_world.py` to add scikit-learn iris classification
3. **Pull request comment-based operation**: Add comment to PR asking to modify file for multiple classification model evaluation

## Prerequisites

### Required Environment Variables

#### For GitHub Testing:
- `GITHUB_PERSONAL_ACCESS_TOKEN`: GitHub Personal Access Token with repo permissions
- `GITHUB_TEST_REPO`: Test repository in format `owner/repo` (e.g., `myuser/test-repo`)

#### For GitLab Testing:
- `GITLAB_PERSONAL_ACCESS_TOKEN`: GitLab Personal Access Token with API permissions
- `GITLAB_TEST_PROJECT`: Test project ID or path (e.g., `123` or `myuser/test-project`)
- `GITLAB_API_URL`: GitLab API URL (defaults to `https://gitlab.com/api/v4`)

#### For LLM:
- `LLM_PROVIDER`: LLM provider to use (default: `openai`)
- `OPENAI_API_KEY`: OpenAI API key (if using OpenAI)
- `OPENAI_BASE_URL`: OpenAI-compatible API base URL (for local LLMs, e.g., `http://localhost:1234/v1`)
- `OPENAI_MODEL`: Model name to use (defaults to `gpt-4o`)

### Repository/Project Setup

The test repository/project should:
- Be accessible with the provided token
- Allow the token to create issues, branches, pull requests, and comments
- Have the following labels (will be created automatically if missing):
  - `coding agent`
  - `coding agent processing`
  - `coding agent done`

## Setup Instructions

### 1. Create Test Repository/Project

#### GitHub:
1. Create a new repository on GitHub (public or private)
2. Note the repository path (e.g., `myuser/coding-agent-test`)
3. Generate a Personal Access Token with `repo` scope

#### GitLab:
1. Create a new project on GitLab (public or private)
2. Note the project ID or path
3. Generate a Personal Access Token with `api` scope

### 2. Configure Environment Variables

Create a `.env` file or set environment variables:

```bash
# For GitHub testing
export GITHUB_PERSONAL_ACCESS_TOKEN="ghp_your_token_here"
export GITHUB_TEST_REPO="yourusername/your-test-repo"

# For GitLab testing
export GITLAB_PERSONAL_ACCESS_TOKEN="glpat-your_token_here"
export GITLAB_TEST_PROJECT="123"  # or "yourusername/your-test-project"
export GITLAB_API_URL="https://gitlab.com/api/v4"

# LLM configuration
export LLM_PROVIDER="openai"
export OPENAI_API_KEY="sk-your_openai_key_here"
```

### 3. Install Dependencies

```bash
# Install required packages
pip install requests pyyaml portalocker
```

## Running the Tests

### Run All Real Integration Tests

```bash
cd /path/to/coding_agent
python tests/run_tests.py --real
```

### Run Individual Test Scenarios

```bash
# Run specific test class
python -m unittest tests.real_integration.test_scenarios.RealIntegrationTestScenarios.test_scenario_1_hello_world_creation

python -m unittest tests.real_integration.test_scenarios.RealIntegrationTestScenarios.test_scenario_2_pull_request_creation

python -m unittest tests.real_integration.test_scenarios.RealIntegrationTestScenarios.test_scenario_3_pr_comment_operation
```

### Debug Mode

Set `DEBUG=true` to enable verbose logging:

```bash
DEBUG=true python tests/run_tests.py --real
```

## Test Scenarios Details

### Scenario 1: Hello World Creation
- Creates an issue with Japanese instructions to create `hello_world.py`
- Runs the coding agent to process the issue
- Verifies that `hello_world.py` is created and outputs "hello world"
- Uses direct commit to main branch

### Scenario 2: Pull Request Creation
- Creates an issue asking to modify `hello_world.py` for scikit-learn iris classification
- Runs the coding agent to create a branch and pull request
- Verifies that a pull request is created with the modifications

### Scenario 3: PR Comment Operation
- Adds a comment to the existing PR asking for multiple model evaluation
- Runs the coding agent to process the comment
- Verifies that the file is updated with accuracy and confusion matrix evaluation

## Verification Methods

The tests use multiple verification approaches:

1. **Direct API verification**: Checks if files exist and have expected content
2. **Execution verification**: Downloads and executes Python files to verify output
3. **LLM-based verification**: Uses LLM to verify non-deterministic content meets criteria
4. **Flexible pattern matching**: Checks for common branch names and PR patterns

## Troubleshooting

### Common Issues

1. **Permission Errors**: Ensure your token has sufficient permissions (repo/api scope)
2. **Repository Not Found**: Verify the repository/project path is correct
3. **Timeout Errors**: Tests may take several minutes; increase timeout if needed
4. **Label Issues**: The framework will try to create required labels automatically

### Debug Information

The tests provide detailed logging:
- Issue creation and status
- Coding agent execution output
- File verification results
- LLM verification responses

### Cleanup

Tests automatically clean up created issues, but you may want to manually:
- Close any remaining open issues
- Delete test branches
- Remove test files from the repository

## Configuration Files

The tests use special configuration files:
- `tests/real_test_config_github.yaml`: GitHub real test configuration
- `tests/real_test_config_gitlab.yaml`: GitLab real test configuration

These are automatically loaded and override default settings for real API usage.

## Safety Considerations

- Use dedicated test repositories/projects
- Don't use production repositories
- Be aware of API rate limits
- Monitor LLM API usage and costs
- Clean up test artifacts regularly

## Example Output

Successful test run:
```
✅ GitHub testing enabled for repository: myuser/test-repo
✅ OpenAI LLM configured

🚀 Running real integration tests...

test_scenario_1_hello_world_creation ... INFO: Created issue #123: Create hello_world.py file with main function
INFO: Running coding agent...
INFO: Waiting for issue processing to complete...
INFO: Verifying hello_world.py file creation...
INFO: Test Scenario 1 completed successfully
ok

test_scenario_2_pull_request_creation ... INFO: Created issue #124: Modify hello_world.py to add scikit-learn iris classification
INFO: Running coding agent...
INFO: Found pull request from branch: feature/iris-classification
INFO: Test Scenario 2 completed successfully
ok

test_scenario_3_pr_comment_operation ... INFO: Added comment to PR #1
INFO: Running coding agent...
INFO: LLM verification verdict: YES
INFO: Test Scenario 3 completed successfully
ok

📊 Test Results:
Tests run: 3
Failures: 0
Errors: 0
```