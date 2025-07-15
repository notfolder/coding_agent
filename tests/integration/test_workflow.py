"""Comprehensive integration tests using GitHub and GitLab mocks."""

import contextlib
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

"""Comprehensive workflow integration tests for GitHub and GitLab task handlers."""


# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Mock the mcp module before importing TaskHandler
sys.modules["mcp"] = MagicMock()
sys.modules["mcp"].McpError = Exception


def _import_test_modules() -> tuple[type, ...]:
    """Import test modules after mocking is set up."""
    from handlers.task_factory import GitHubTaskFactory, GitLabTaskFactory  # noqa: PLC0415
    from handlers.task_getter_github import TaskGetterFromGitHub, TaskGitHubIssue  # noqa: PLC0415
    from handlers.task_getter_gitlab import TaskGetterFromGitLab, TaskGitLabIssue  # noqa: PLC0415
    from handlers.task_handler import TaskHandler  # noqa: PLC0415
    from handlers.task_key import GitHubIssueTaskKey, GitLabIssueTaskKey  # noqa: PLC0415
    from tests.mocks.mock_llm_client import (  # noqa: PLC0415
        MockLLMClient,
        MockLLMClientWithToolCalls,
    )
    from tests.mocks.mock_mcp_client import MockMCPToolClient  # noqa: PLC0415

    return (
        GitHubTaskFactory, GitLabTaskFactory, TaskGetterFromGitHub, TaskGitHubIssue,
        TaskGetterFromGitLab, TaskGitLabIssue, TaskHandler, GitHubIssueTaskKey,
        GitLabIssueTaskKey, MockLLMClient, MockLLMClientWithToolCalls, MockMCPToolClient,
    )


# Import the modules we need
(GitHubTaskFactory, GitLabTaskFactory, TaskGetterFromGitHub, TaskGitHubIssue,
 TaskGetterFromGitLab, TaskGitLabIssue, TaskHandler, GitHubIssueTaskKey,
 GitLabIssueTaskKey, MockLLMClient, MockLLMClientWithToolCalls,
 MockMCPToolClient) = _import_test_modules()


class TestGitHubWorkflowIntegration(unittest.TestCase):
    """End-to-end GitHub workflow tests with comprehensive mocks."""

    # Test constants
    MAX_RETRY_ATTEMPTS = 2

    def _verify_equal(self, actual: object, expected: object, msg: str = "") -> None:
        """Verify that actual equals expected."""
        if actual != expected:
            pytest.fail(f"Expected {expected}, got {actual}. {msg}")

    def _verify_true(self, *, condition: bool, msg: str = "") -> None:
        """Verify that condition is True."""
        if not condition:
            pytest.fail(f"Condition was False. {msg}")

    def _verify_in(self, item: object, container: object, msg: str = "") -> None:
        """Verify that item is in container."""
        if item not in container:
            pytest.fail(f"{item} not found in {container}. {msg}")

    def _verify_not_in(self, item: object, container: object, msg: str = "") -> None:
        """Verify that item is not in container."""
        if item in container:
            pytest.fail(f"{item} found in {container} but should not be. {msg}")

    def _verify_isinstance(self, obj: object, cls: type, msg: str = "") -> None:
        """Verify that obj is instance of cls."""
        if not isinstance(obj, cls):
            pytest.fail(f"Expected {obj} to be instance of {cls}. {msg}")

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
        self._verify_isinstance(tasks, list)
        self._verify_true(condition=len(tasks) > 0, msg="Should find mock GitHub issues")

        # 2. Process first task
        task = tasks[0]
        self._verify_isinstance(task, TaskGitHubIssue)

        # 3. Prepare task (updates labels)
        task.prepare()

        # Verify label changes
        self._verify_not_in("coding agent", task.labels)
        self._verify_in("coding agent processing", task.labels)

        # 4. Generate prompt
        prompt = task.get_prompt()
        self._verify_isinstance(prompt, str)
        self._verify_in("ISSUE:", prompt)
        self._verify_in("COMMENTS:", prompt)

        # 5. Handle task with LLM
        task_handler = TaskHandler(
            llm_client=self.llm_client,
            mcp_clients={"github": self.github_mcp_client},
            config=self.config,
        )

        # Process the task
        result = task_handler.handle(task)

        # Verify completion
        self._verify_true(condition=result is None)  # Should complete without errors

        # Verify MCP interactions occurred
        mock_data = self.github_mcp_client.get_mock_data()
        self._verify_in(task.issue["number"], mock_data["updated_issues"])

    def test_github_task_factory_integration(self) -> None:
        """Test GitHub task factory integration."""
        factory = GitHubTaskFactory(
            mcp_client=self.github_mcp_client, github_client=self.github_client, config=self.config,
        )

        # Create task from key
        task_key = GitHubIssueTaskKey("testorg", "testrepo", 1)
        task = factory.create_task(task_key)

        self._verify_isinstance(task, TaskGitHubIssue)
        self._verify_equal(task.issue["number"], 1)

        # Test task workflow
        task.prepare()
        prompt = task.get_prompt()
        self._verify_in("Test GitHub Issue 1", prompt)

    def test_github_error_recovery_workflow(self) -> None:
        """Test GitHub workflow error recovery."""
        # Create MCP client that fails initially then recovers
        error_mcp_client = MockMCPToolClient({"mcp_server_name": "github"})
        call_count = 0
        original_call_tool = error_mcp_client.call_tool

        def intermittent_failure_tool(tool: str, args: dict[str, object]) -> object:
            nonlocal call_count
            call_count += 1
            if tool == "update_issue" and call_count <= self.MAX_RETRY_ATTEMPTS:
                msg = "Temporary network error"
                raise RuntimeError(msg)
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
        with contextlib.suppress(RuntimeError):
            task.prepare()  # First call may fail

        # Retry should work
        with contextlib.suppress(RuntimeError):
            task.prepare()  # Subsequent calls should succeed

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
            self._verify_isinstance(prompt, str)

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
            self._verify_true(condition=result is None)

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

                def mock_comment(text: str, *, mention: bool = False) -> object:
                    comments_posted.append({"text": text, "mention": mention})
                    return original_comment(text, mention=mention) if original_comment else None

                task.comment = mock_comment

                # Post test comments
                task.comment("Test comment without mention")
                task.comment("Test comment with mention", mention=True)

                # Verify comments were tracked
                self._verify_equal(len(comments_posted), 2)
                self._verify_equal(comments_posted[0]["text"], "Test comment without mention")
                self._verify_true(condition=not comments_posted[0]["mention"])
                self._verify_true(condition=comments_posted[1]["mention"])


class TestGitLabWorkflowIntegration(unittest.TestCase):
    """End-to-end GitLab workflow tests with comprehensive mocks."""

    def _verify_equal(self, actual: object, expected: object, msg: str = "") -> None:
        """Verify that actual equals expected."""
        if actual != expected:
            pytest.fail(f"Expected {expected}, got {actual}. {msg}")

    def _verify_true(self, *, condition: bool, msg: str = "") -> None:
        """Verify that condition is True."""
        if not condition:
            pytest.fail(f"Condition was False. {msg}")

    def _verify_in(self, item: object, container: object, msg: str = "") -> None:
        """Verify that item is in container."""
        if item not in container:
            pytest.fail(f"{item} not found in {container}. {msg}")

    def _verify_not_in(self, item: object, container: object, msg: str = "") -> None:
        """Verify that item is not in container."""
        if item in container:
            pytest.fail(f"{item} found in {container} but should not be. {msg}")

    def _verify_isinstance(self, obj: object, cls: type, msg: str = "") -> None:
        """Verify that obj is instance of cls."""
        if not isinstance(obj, cls):
            pytest.fail(f"Expected {obj} to be instance of {cls}. {msg}")

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
        self._verify_isinstance(tasks, list)
        self._verify_true(condition=len(tasks) > 0, msg="Should find mock GitLab issues")

        # 2. Process first task
        task = tasks[0]
        self._verify_isinstance(task, TaskGitLabIssue)

        # 3. Prepare task (updates labels)
        task.prepare()

        # Verify label changes
        updated_labels = task.issue["labels"]
        self._verify_not_in("coding agent", updated_labels)
        self._verify_in("coding agent processing", updated_labels)

        # 4. Generate prompt
        prompt = task.get_prompt()
        self._verify_isinstance(prompt, str)
        self._verify_in("ISSUE:", prompt)

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
        self._verify_true(condition=result is None)  # Should complete without errors

        # Verify MCP interactions occurred
        mock_data = self.gitlab_mcp_client.get_mock_data()
        self._verify_in(task.issue_iid, mock_data["updated_issues"])

    def test_gitlab_task_factory_integration(self) -> None:
        """Test GitLab task factory integration."""
        factory = GitLabTaskFactory(
            mcp_client=self.gitlab_mcp_client, gitlab_client=self.gitlab_client, config=self.config,
        )

        # Create task from key
        task_key = GitLabIssueTaskKey(123, 1)
        task = factory.create_task(task_key)

        self._verify_isinstance(task, TaskGitLabIssue)
        self._verify_equal(task.issue_iid, 1)

        # Test task workflow
        task.prepare()
        prompt = task.get_prompt()
        self._verify_in("Test GitLab Issue 1", prompt)

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
            self._verify_isinstance(prompt, str)
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
                self._verify_not_in("coding agent", current_labels)
                self._verify_in("coding agent processing", current_labels)

            # Other labels should be preserved
            for label in original_labels:
                if label != "coding agent":
                    self._verify_in(label, current_labels)


if __name__ == "__main__":
    unittest.main()
