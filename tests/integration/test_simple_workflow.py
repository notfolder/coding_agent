"""Simple integration test for GitHub and GitLab workflows."""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

# Mock the mcp module before importing TaskHandler
sys.modules["mcp"] = MagicMock()
sys.modules["mcp"].McpError = Exception

from handlers.task_getter_github import TaskGetterFromGitHub, TaskGitHubIssue
from handlers.task_getter_gitlab import TaskGetterFromGitLab, TaskGitLabIssue
from handlers.task_handler import TaskHandler
from tests.mocks.mock_llm_client import MockLLMClient
from tests.mocks.mock_mcp_client import MockMCPToolClient


class TestSimpleWorkflow(unittest.TestCase):
    """Simple workflow integration test."""

    def setUp(self) -> None:
        """Set up test environment."""
        self.config = {
            "github": {
                "owner": "testorg",
                "repo": "testrepo",
                "query": 'label:"coding agent"',
                "bot_label": "coding agent",
                "processing_label": "coding agent processing",
                "done_label": "coding agent done",
            },
            "gitlab": {
                "project_id": 123,
                "bot_label": "coding agent",
                "processing_label": "coding agent processing",
                "done_label": "coding agent done",
                "owner": "testuser",
            },
            "max_llm_process_num": 20,
        }

        # Create mock clients
        self.github_mcp_client = MockMCPToolClient({"mcp_server_name": "github"})
        self.gitlab_mcp_client = MockMCPToolClient({"mcp_server_name": "gitlab"})
        self.llm_client = MockLLMClient(self.config)

    def test_basic_integration_workflow(self) -> None:
        """Test basic integration workflow."""
        # Set up simple LLM response
        self.llm_client.set_mock_response({"comment": "Integration test completed", "done": True})

        # Create task handler with multiple MCP clients
        task_handler = TaskHandler(
            llm_client=self.llm_client,
            mcp_clients={"github": self.github_mcp_client, "gitlab": self.gitlab_mcp_client},
            config=self.config,
        )

        # Create a simple GitHub task
        sample_issue = self.github_mcp_client.get_mock_data()["issues"][0]
        github_task = TaskGitHubIssue(
            issue=sample_issue,
            mcp_client=self.github_mcp_client,
            github_client=MagicMock(),
            config=self.config,
        )

        # Process the task
        result = task_handler.handle(github_task)

        # Should complete without errors
        assert result is None


if __name__ == "__main__":
    unittest.main()
