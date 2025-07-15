"""Comprehensive unit tests for TaskHandler using mocks."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Mock the mcp module before importing TaskHandler
sys.modules["mcp"] = MagicMock()
sys.modules["mcp"].McpError = Exception


def _import_test_modules() -> tuple[type, ...]:
    """Import test modules after mocking is set up."""
    import pytest
    from mcp import McpError

    from handlers.task_getter_github import TaskGitHubIssue
    from handlers.task_getter_gitlab import TaskGitLabIssue
    from handlers.task_handler import TaskHandler
    from tests.mocks.mock_llm_client import (
        MockLLMClient,
        MockLLMClientWithErrors,
        MockLLMClientWithToolCalls,
    )
    from tests.mocks.mock_mcp_client import MockMCPToolClient

    return (pytest, McpError, TaskGitHubIssue, TaskGitLabIssue, TaskHandler,
            MockLLMClient, MockLLMClientWithErrors, MockLLMClientWithToolCalls,
            MockMCPToolClient)


# Import the modules we need
(pytest, McpError, TaskGitHubIssue, TaskGitLabIssue, TaskHandler,
 MockLLMClient, MockLLMClientWithErrors, MockLLMClientWithToolCalls,
 MockMCPToolClient) = _import_test_modules()

# Constants
MAX_TOOL_FAILURES = 2


class TestTaskHandler(unittest.TestCase):
    """Test TaskHandler functionality with mock components."""

    def setUp(self) -> None:
        """Set up test environment."""
        self.config = {
            "github": {
                "owner": "testorg",
                "repo": "testrepo",
                "bot_label": "coding agent",
                "processing_label": "coding agent processing",
                "done_label": "coding agent done",
            },
            "max_llm_process_num": 10,
        }

        # Create mock MCP clients
        github_server_config = {"mcp_server_name": "github"}
        self.github_mcp_client = MockMCPToolClient(github_server_config)

        # Create mock LLM client
        self.llm_client = MockLLMClient(self.config)

        # Create sample GitHub task
        sample_github_issue = {
            "number": 1,
            "title": "Test Issue",
            "body": "Test issue body",
            "repository_url": "https://api.github.com/repos/testorg/testrepo",
            "labels": [{"name": "coding agent", "color": "blue"}],
        }

        self.github_task = TaskGitHubIssue(
            issue=sample_github_issue,
            mcp_client=self.github_mcp_client,
            github_client=MagicMock(),
            config=self.config,
        )

    def test_task_handler_creation(self) -> None:
        """Test TaskHandler object creation."""
        task_handler = TaskHandler(
            llm_client=self.llm_client,
            mcp_clients={"github": self.github_mcp_client},
            config=self.config,
        )

        assert task_handler.llm_client is not None
        assert task_handler.mcp_clients is not None
        assert task_handler.config is not None

    def test_sanitize_arguments_dict(self) -> None:
        """Test argument sanitization with dict input."""
        task_handler = TaskHandler(
            llm_client=self.llm_client,
            mcp_clients={"github": self.github_mcp_client},
            config=self.config,
        )

        # Test with valid dict
        args_dict = {"owner": "testorg", "repo": "testrepo", "issue_number": 1}
        sanitized = task_handler.sanitize_arguments(args_dict)
        assert sanitized == args_dict

    def test_sanitize_arguments_json_string(self) -> None:
        """Test argument sanitization with JSON string input."""
        task_handler = TaskHandler(
            llm_client=self.llm_client,
            mcp_clients={"github": self.github_mcp_client},
            config=self.config,
        )

        # Test with valid JSON string
        args_json = '{"owner": "testorg", "repo": "testrepo", "issue_number": 1}'
        sanitized = task_handler.sanitize_arguments(args_json)
        expected = {"owner": "testorg", "repo": "testrepo", "issue_number": 1}
        assert sanitized == expected

    def test_sanitize_arguments_invalid_json(self) -> None:
        """Test argument sanitization with invalid JSON."""
        task_handler = TaskHandler(
            llm_client=self.llm_client,
            mcp_clients={"github": self.github_mcp_client},
            config=self.config,
        )

        # Test with invalid JSON
        with pytest.raises(ValueError, match="Invalid JSON string for arguments"):
            task_handler.sanitize_arguments('{"invalid": json}')

    def test_sanitize_arguments_invalid_type(self) -> None:
        """Test argument sanitization with invalid type."""
        task_handler = TaskHandler(
            llm_client=self.llm_client,
            mcp_clients={"github": self.github_mcp_client},
            config=self.config,
        )

        # Test with invalid type
        with pytest.raises(TypeError):
            task_handler.sanitize_arguments(123)

    def test_handle_task_basic_workflow(self) -> None:
        """Test basic task handling workflow."""
        # Set up LLM client with completion response
        self.llm_client.set_mock_response({"comment": "Task completed successfully", "done": True})

        task_handler = TaskHandler(
            llm_client=self.llm_client,
            mcp_clients={"github": self.github_mcp_client},
            config=self.config,
        )

        # Handle the task
        result = task_handler.handle(self.github_task)

        # Should complete without errors
        assert result is None  # handle() method returns None on completion

    def test_handle_task_with_tool_calls(self) -> None:
        """Test task handling with tool calls."""
        # Use LLM client that makes tool calls
        tool_call_llm = MockLLMClientWithToolCalls(self.config)

        task_handler = TaskHandler(
            llm_client=tool_call_llm,
            mcp_clients={"github": self.github_mcp_client},
            config=self.config,
        )

        # Handle the task
        result = task_handler.handle(self.github_task)

        # Should complete after making tool calls
        assert result is None

    def test_handle_task_with_think_tags(self) -> None:
        """Test handling of <think> tags in LLM responses."""
        # Set up LLM response with think tags
        think_response = "<think>Let me analyze this issue</think>\n" + json.dumps(
            {"comment": "After thinking, I understand the issue", "done": True},
        )

        self.llm_client.set_custom_responses([(think_response, [])])

        task_handler = TaskHandler(
            llm_client=self.llm_client,
            mcp_clients={"github": self.github_mcp_client},
            config=self.config,
        )

        # Mock the task's comment method to verify think content is posted
        self.github_task.comment = MagicMock()

        # Handle the task
        task_handler.handle(self.github_task)

        # Verify that think content was posted as comment
        # Check that comment was called with the think content
        # (may have mention=True due to task logic)
        self.github_task.comment.assert_called()

    def test_handle_task_with_errors(self) -> None:
        """Test task handling with LLM errors."""
        # Use error-prone LLM client
        error_llm = MockLLMClientWithErrors(self.config)

        task_handler = TaskHandler(
            llm_client=error_llm,
            mcp_clients={"github": self.github_mcp_client},
            config=self.config,
        )

        # Handle the task (should handle errors gracefully)
        try:
            task_handler.handle(self.github_task)
            # If it completes, that's good error handling
        except (OSError, RuntimeError) as e:
            # Should not raise unhandled exceptions
            self.fail(f"TaskHandler should handle errors gracefully, but got: {e}")

    def test_handle_task_max_iterations(self) -> None:
        """Test task handling with maximum iteration limit."""
        # Set up LLM that never completes (done=False always)
        never_done_responses = [
            (json.dumps({"comment": f"Still working... {i}", "done": False}), [])
            for i in range(15)  # More than max_llm_process_num
        ]
        self.llm_client.set_custom_responses(never_done_responses)

        # Set a low max iteration count for testing
        config_with_low_max = self.config.copy()
        config_with_low_max["max_llm_process_num"] = 5

        task_handler = TaskHandler(
            llm_client=self.llm_client,
            mcp_clients={"github": self.github_mcp_client},
            config=config_with_low_max,
        )

        # Handle the task (should stop after max iterations)
        result = task_handler.handle(self.github_task)

        # Should stop due to max iterations
        assert result is None

    def test_handle_task_with_invalid_json_responses(self) -> None:
        """Test handling of invalid JSON responses from LLM."""
        # Set up invalid JSON responses
        invalid_responses = [
            ("Invalid JSON {", []),
            ("Another invalid response", []),
            (json.dumps({"comment": "Finally valid", "done": True}), []),
        ]
        self.llm_client.set_custom_responses(invalid_responses)

        task_handler = TaskHandler(
            llm_client=self.llm_client,
            mcp_clients={"github": self.github_mcp_client},
            config=self.config,
        )

        # Handle the task (should handle invalid JSON gracefully)
        try:
            task_handler.handle(self.github_task)
            # Should eventually complete with valid response
        except (OSError, RuntimeError) as e:
            # Should not crash on invalid JSON
            self.fail(f"TaskHandler should handle invalid JSON gracefully, but got: {e}")

    def test_handle_task_tool_error_management(self) -> None:
        """Test tool error management and retry logic."""
        # Create MCP client that fails on first few calls
        error_mcp_client = MockMCPToolClient({"mcp_server_name": "github"})
        call_count = 0
        original_call_tool = error_mcp_client.call_tool

        def failing_call_tool(tool: str, args: dict[str, Any]) -> dict[str, Any] | None:
            nonlocal call_count
            call_count += 1
            if call_count <= MAX_TOOL_FAILURES:  # Fail first 2 calls
                msg = "Tool call failed"
                # Use nested exception structure for compatibility
                raise RuntimeError(msg) from McpError("Tool call failed")
            return original_call_tool(tool, args)

        error_mcp_client.call_tool = failing_call_tool

        # Set up LLM to make tool calls
        tool_responses = [
            (
                json.dumps(
                    {
                        "command": {"tool": "github_get_issue", "args": {"issue_number": 1}},
                        "comment": "Getting issue details",
                        "done": False,
                    },
                ),
                [],
            ),
            (
                json.dumps(
                    {
                        "command": {"tool": "github_get_issue", "args": {"issue_number": 1}},
                        "comment": "Retrying to get issue details",
                        "done": False,
                    },
                ),
                [],
            ),
            (
                json.dumps(
                    {
                        "command": {"tool": "github_get_issue", "args": {"issue_number": 1}},
                        "comment": "Finally got issue details",
                        "done": False,
                    },
                ),
                [],
            ),
            (json.dumps({"comment": "Task completed", "done": True}), []),
        ]
        self.llm_client.set_custom_responses(tool_responses)

        task_handler = TaskHandler(
            llm_client=self.llm_client,
            mcp_clients={"github": error_mcp_client},
            config=self.config,
        )

        # Handle the task - should complete without crashing
        task_handler.handle(self.github_task)

        # Verify that tool was called multiple times due to retries
        assert call_count >= MAX_TOOL_FAILURES

    def test_make_system_prompt(self) -> None:
        """Test system prompt generation."""
        task_handler = TaskHandler(
            llm_client=self.llm_client,
            mcp_clients={"github": self.github_mcp_client},
            config=self.config,
        )

        # Test that system prompt is generated
        system_prompt = task_handler.get_system_prompt()
        assert isinstance(system_prompt, str)
        assert len(system_prompt) > 0


class TestTaskHandlerWithDifferentTasks(unittest.TestCase):
    """Test TaskHandler with different types of tasks."""

    def setUp(self) -> None:
        """Set up test environment."""
        self.config = {
            "gitlab": {
                "project_id": 123,
                "bot_label": "coding agent",
                "processing_label": "coding agent processing",
                "done_label": "coding agent done",
            },
            "max_llm_process_num": 10,
        }

        # Create mock GitLab components
        gitlab_server_config = {"mcp_server_name": "gitlab"}
        self.gitlab_mcp_client = MockMCPToolClient(gitlab_server_config)
        self.llm_client = MockLLMClient(self.config)

        # Create sample GitLab task
        sample_gitlab_issue = {
            "iid": 1,
            "title": "Test GitLab Issue",
            "description": "Test GitLab issue description",
            "project_id": 123,
            "labels": ["coding agent"],
        }

        self.gitlab_task = TaskGitLabIssue(
            issue=sample_gitlab_issue,
            mcp_client=self.gitlab_mcp_client,
            gitlab_client=MagicMock(),
            config=self.config,
        )

    def test_handle_gitlab_task(self) -> None:
        """Test handling GitLab tasks."""
        self.llm_client.set_mock_response({"comment": "GitLab task completed", "done": True})

        task_handler = TaskHandler(
            llm_client=self.llm_client,
            mcp_clients={"gitlab": self.gitlab_mcp_client},
            config=self.config,
        )

        # Handle GitLab task
        result = task_handler.handle(self.gitlab_task)
        assert result is None  # Should complete successfully

    def test_handle_task_with_multiple_mcp_clients(self) -> None:
        """Test task handling with multiple MCP clients."""
        # Create both GitHub and GitLab MCP clients
        github_mcp = MockMCPToolClient({"mcp_server_name": "github"})
        gitlab_mcp = MockMCPToolClient({"mcp_server_name": "gitlab"})

        self.llm_client.set_mock_response(
            {"comment": "Task completed with multiple MCP clients", "done": True},
        )

        task_handler = TaskHandler(
            llm_client=self.llm_client,
            mcp_clients={"github": github_mcp, "gitlab": gitlab_mcp},
            config=self.config,
        )

        # Handle task
        result = task_handler.handle(self.gitlab_task)
        assert result is None


if __name__ == "__main__":
    unittest.main()
