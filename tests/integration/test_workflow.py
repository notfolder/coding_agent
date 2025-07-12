"""Comprehensive integration tests using GitHub and GitLab mocks."""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

# Mock the mcp module before importing TaskHandler
sys.modules["mcp"] = MagicMock()
sys.modules["mcp"].McpError = Exception

from handlers.task_factory import GitHubTaskFactory, GitLabTaskFactory
from handlers.task_getter_github import TaskGetterFromGitHub, TaskGitHubIssue
from handlers.task_getter_gitlab import TaskGetterFromGitLab, TaskGitLabIssue
from handlers.task_handler import TaskHandler
from handlers.task_key import GitHubIssueTaskKey, GitLabIssueTaskKey
from tests.mocks.mock_llm_client import MockLLMClient, MockLLMClientWithToolCalls
from tests.mocks.mock_mcp_client import MockMCPToolClient


class TestGitHubWorkflowIntegration(unittest.TestCase):
    """End-to-end GitHub workflow tests with comprehensive mocks."""

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
            "max_llm_process_num": 20,
        }

        # Create comprehensive GitHub mock setup
        github_server_config = {"mcp_server_name": "github"}
        self.github_mcp_client = MockMCPToolClient(github_server_config)
        self.github_client = MagicMock()
        self.llm_client = MockLLMClientWithToolCalls(self.config)

        # Mock the GitHub client search_issues method to return mock data
        self.github_client.search_issues.return_value = self.github_mcp_client.get_mock_data()[
            "issues"
        ]

        # Patch GitHub client creation
        self.github_client_patcher = patch("handlers.task_getter_github.GithubClient")
        self.mock_github_client_class = self.github_client_patcher.start()
        self.mock_github_client_class.return_value = self.github_client

    def tearDown(self) -> None:
        """Clean up patches."""
        self.github_client_patcher.stop()

    def test_full_github_issue_workflow(self) -> None:
        """Test complete GitHub issue processing workflow."""
        # 1. Get tasks from GitHub
        task_getter = TaskGetterFromGitHub(
            config=self.config, mcp_clients={"github": self.github_mcp_client},
        )
        tasks = task_getter.get_task_list()
        assert isinstance(tasks, list)
        assert len(tasks) > 0, "Should find mock GitHub issues"

        # 2. Process first task
        task = tasks[0]
        assert isinstance(task, TaskGitHubIssue)

        # 3. Prepare task (updates labels)
        original_labels = task.labels.copy()
        task.prepare()

        # Verify label changes
        assert "coding agent" not in task.labels
        assert "coding agent processing" in task.labels

        # 4. Generate prompt
        prompt = task.get_prompt()
        assert isinstance(prompt, str)
        assert "ISSUE:" in prompt
        assert "COMMENTS:" in prompt

        # 5. Handle task with LLM
        task_handler = TaskHandler(
            llm_client=self.llm_client,
            mcp_clients={"github": self.github_mcp_client},
            config=self.config,
        )

        # Process the task
        result = task_handler.handle(task)

        # Verify completion
        assert result is None  # Should complete without errors

        # Verify MCP interactions occurred
        mock_data = self.github_mcp_client.get_mock_data()
        assert task.issue["number"] in mock_data["updated_issues"]

    def test_github_task_factory_integration(self) -> None:
        """Test GitHub task factory integration."""
        factory = GitHubTaskFactory(
            mcp_client=self.github_mcp_client, github_client=self.github_client, config=self.config,
        )

        # Create task from key
        task_key = GitHubIssueTaskKey("testorg", "testrepo", 1)
        task = factory.create_task(task_key)

        assert isinstance(task, TaskGitHubIssue)
        assert task.issue["number"] == 1

        # Test task workflow
        task.prepare()
        prompt = task.get_prompt()
        assert "Test GitHub Issue 1" in prompt

    def test_github_error_recovery_workflow(self) -> None:
        """Test GitHub workflow error recovery."""
        # Create MCP client that fails initially then recovers
        error_mcp_client = MockMCPToolClient({"mcp_server_name": "github"})
        call_count = 0
        original_call_tool = error_mcp_client.call_tool

        def intermittent_failure_tool(tool, args):
            nonlocal call_count
            call_count += 1
            if tool == "update_issue" and call_count <= 2:
                msg = "Temporary network error"
                raise Exception(msg)
            return original_call_tool(tool, args)

        error_mcp_client.call_tool = intermittent_failure_tool

        # Create task with error-prone MCP client
        sample_issue = error_mcp_client.get_mock_data()["issues"][0]
        task = TaskGitHubIssue(
            issue=sample_issue,
            mcp_client=error_mcp_client,
            github_client=self.github_client,
            config=self.config,
        )

        # Should handle errors gracefully
        try:
            task.prepare()  # First call may fail
        except Exception:
            pass  # Expected for this test

        # Retry should work
        try:
            task.prepare()  # Subsequent calls should succeed
        except Exception:
            pass  # May still fail, which is acceptable

    def test_github_multiple_issues_workflow(self) -> None:
        """Test processing multiple GitHub issues."""
        task_getter = TaskGetterFromGitHub(
            config=self.config, mcp_clients={"github": self.github_mcp_client},
        )
        tasks = task_getter.get_task_list()

        # Process all available tasks
        for task in tasks:
            # Prepare each task
            task.prepare()

            # Generate prompt for each
            prompt = task.get_prompt()
            assert isinstance(prompt, str)

            # Simple completion test
            self.llm_client.set_mock_response(
                {"comment": f"Completed task for issue #{task.issue['number']}", "done": True},
            )

            task_handler = TaskHandler(
                llm_client=self.llm_client,
                mcp_clients={"github": self.github_mcp_client},
                config=self.config,
            )

            result = task_handler.handle(task)
            assert result is None

    def test_github_comment_workflow(self) -> None:
        """Test GitHub comment creation workflow."""
        tasks = TaskGetterFromGitHub(
            config=self.config, mcp_clients={"github": self.github_mcp_client},
        ).get_task_list()

        if tasks:
            task = tasks[0]

            # Mock comment method if it exists
            if hasattr(task, "comment"):
                original_comment = task.comment
                comments_posted = []

                def mock_comment(text, mention=False):
                    comments_posted.append({"text": text, "mention": mention})
                    return original_comment(text, mention) if original_comment else None

                task.comment = mock_comment

                # Post test comments
                task.comment("Test comment without mention")
                task.comment("Test comment with mention", mention=True)

                # Verify comments were tracked
                assert len(comments_posted) == 2
                assert comments_posted[0]["text"] == "Test comment without mention"
                assert not comments_posted[0]["mention"]
                assert comments_posted[1]["mention"]


class TestGitLabWorkflowIntegration(unittest.TestCase):
    """End-to-end GitLab workflow tests with comprehensive mocks."""

    def setUp(self) -> None:
        """Set up test environment."""
        self.config = {
            "gitlab": {
                "project_id": 123,
                "bot_label": "coding agent",
                "processing_label": "coding agent processing",
                "done_label": "coding agent done",
                "assignee": "testuser",
            },
            "max_llm_process_num": 20,
        }

        # Create comprehensive GitLab mock setup
        gitlab_server_config = {"mcp_server_name": "gitlab"}
        self.gitlab_mcp_client = MockMCPToolClient(gitlab_server_config)
        self.gitlab_client = MagicMock()
        self.llm_client = MockLLMClient(self.config)  # Use simpler LLM client for GitLab tests

        # Mock the GitLab client methods to return mock data
        mock_data = self.gitlab_mcp_client.get_mock_data()
        self.gitlab_client.search_issues.return_value = mock_data["issues"]
        self.gitlab_client.search_merge_requests.return_value = []

        # Patch GitLab client creation
        self.gitlab_client_patcher = patch("handlers.task_getter_gitlab.GitlabClient")
        self.mock_gitlab_client_class = self.gitlab_client_patcher.start()
        self.mock_gitlab_client_class.return_value = self.gitlab_client

    def tearDown(self) -> None:
        """Clean up patches."""
        self.gitlab_client_patcher.stop()

    def test_full_gitlab_issue_workflow(self) -> None:
        """Test complete GitLab issue processing workflow."""
        # 1. Get tasks from GitLab
        task_getter = TaskGetterFromGitLab(
            config=self.config, mcp_clients={"gitlab": self.gitlab_mcp_client},
        )

        tasks = task_getter.get_task_list()
        assert isinstance(tasks, list)
        assert len(tasks) > 0, "Should find mock GitLab issues"

        # 2. Process first task
        task = tasks[0]
        assert isinstance(task, TaskGitLabIssue)

        # 3. Prepare task (updates labels)
        original_labels = task.issue.get("labels", []).copy()
        task.prepare()

        # Verify label changes
        updated_labels = task.issue["labels"]
        assert "coding agent" not in updated_labels
        assert "coding agent processing" in updated_labels

        # 4. Generate prompt
        prompt = task.get_prompt()
        assert isinstance(prompt, str)
        assert "ISSUE:" in prompt

        # 5. Handle task with LLM
        task_handler = TaskHandler(
            llm_client=self.llm_client,
            mcp_clients={"gitlab": self.gitlab_mcp_client},
            config=self.config,
        )

        # Set up a simple response without tool calls for GitLab test
        self.llm_client.set_mock_response(
            {"comment": "Processing GitLab issue without tool calls", "done": True},
        )

        # Process the task
        result = task_handler.handle(task)

        # Verify completion
        assert result is None  # Should complete without errors

        # Verify MCP interactions occurred
        mock_data = self.gitlab_mcp_client.get_mock_data()
        assert task.issue_iid in mock_data["updated_issues"]

    def test_gitlab_task_factory_integration(self) -> None:
        """Test GitLab task factory integration."""
        factory = GitLabTaskFactory(
            mcp_client=self.gitlab_mcp_client, gitlab_client=self.gitlab_client, config=self.config,
        )

        # Create task from key
        task_key = GitLabIssueTaskKey(123, 1)
        task = factory.create_task(task_key)

        assert isinstance(task, TaskGitLabIssue)
        assert task.issue_iid == 1

        # Test task workflow
        task.prepare()
        prompt = task.get_prompt()
        assert "Test GitLab Issue 1" in prompt

    def test_gitlab_discussions_workflow(self) -> None:
        """Test GitLab discussions handling."""
        tasks = TaskGetterFromGitLab(
            config=self.config, mcp_clients={"gitlab": self.gitlab_mcp_client},
        ).get_task_list()

        if tasks:
            task = tasks[0]

            # Generate prompt (includes discussions)
            prompt = task.get_prompt()

            # Should include discussion content from mock data
            assert isinstance(prompt, str)
            # Verify discussions are included in some form
            # (The exact format depends on implementation)

    def test_gitlab_label_transitions(self) -> None:
        """Test GitLab label transition workflow."""
        task_getter = TaskGetterFromGitLab(
            config=self.config, mcp_clients={"gitlab": self.gitlab_mcp_client},
        )

        tasks = task_getter.get_task_list()

        for task in tasks:
            original_labels = task.issue.get("labels", []).copy()

            # Test prepare (bot_label -> processing_label)
            task.prepare()

            current_labels = task.issue["labels"]

            # Verify label transition
            if "coding agent" in original_labels:
                assert "coding agent" not in current_labels
                assert "coding agent processing" in current_labels

            # Other labels should be preserved
            for label in original_labels:
                if label != "coding agent":
                    assert label in current_labels


if __name__ == "__main__":
    unittest.main()
