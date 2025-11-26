"""Unit tests for task stop functionality."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from handlers.task_key import GitHubIssueTaskKey
from task_stop_manager import TaskStopManager


class MockTask:
    """Mock task for testing."""

    def __init__(self, task_key: GitHubIssueTaskKey, number: int = 1) -> None:
        """Initialize mock task."""
        self.uuid = "test-uuid-123"
        self.user = "testuser"
        self._task_key = task_key
        self.number = number
        self.is_resumed = False
        self.comments: list[str] = []
        self.labels: list[str] = ["coding agent processing"]
        self._assignees: list[str] = ["coding-agent-bot"]

    def get_task_key(self) -> GitHubIssueTaskKey:
        """Get task key."""
        return self._task_key

    def comment(self, text: str, mention: bool = False) -> None:
        """Add a comment."""
        self.comments.append(text)

    def add_label(self, label: str) -> None:
        """Add a label."""
        if label not in self.labels:
            self.labels.append(label)

    def remove_label(self, label: str) -> None:
        """Remove a label."""
        if label in self.labels:
            self.labels.remove(label)

    def get_assignees(self) -> list[str]:
        """Get assignees."""
        return self._assignees

    def refresh_assignees(self) -> list[str]:
        """Refresh assignees from API."""
        return self._assignees


class TestTaskStopManager(unittest.TestCase):
    """Test TaskStopManager functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.config = {
            "task_stop": {
                "enabled": True,
                "check_interval": 1,
                "min_check_interval_seconds": 0,  # Set to 0 for immediate checks in tests
            },
            "context_storage": {
                "base_dir": str(self.temp_dir / "contexts"),
            },
            "github": {
                "processing_label": "coding agent processing",
                "stopped_label": "coding agent stopped",
                "bot_name": "coding-agent-bot",
            },
        }
        self.manager = TaskStopManager(self.config)

        # Create contexts directories
        self.contexts_dir = self.temp_dir / "contexts"
        self.running_dir = self.contexts_dir / "running"
        self.completed_dir = self.contexts_dir / "completed"
        self.running_dir.mkdir(parents=True, exist_ok=True)
        self.completed_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_check_assignee_status_bot_assigned(self):
        """Test that check_assignee_status returns True when bot is assigned."""
        task_key = GitHubIssueTaskKey("owner", "repo", 123)
        task = MockTask(task_key)
        task._assignees = ["coding-agent-bot", "other-user"]

        result = self.manager.check_assignee_status(task)
        self.assertTrue(result)

    def test_check_assignee_status_bot_unassigned(self):
        """Test that check_assignee_status returns False when bot is unassigned."""
        task_key = GitHubIssueTaskKey("owner", "repo", 123)
        task = MockTask(task_key)
        task._assignees = ["other-user"]

        result = self.manager.check_assignee_status(task)
        self.assertFalse(result)

    def test_check_assignee_status_no_assignees(self):
        """Test that check_assignee_status returns False when no one is assigned."""
        task_key = GitHubIssueTaskKey("owner", "repo", 123)
        task = MockTask(task_key)
        task._assignees = []

        result = self.manager.check_assignee_status(task)
        self.assertFalse(result)

    def test_check_assignee_status_disabled(self):
        """Test that check_assignee_status returns True when disabled."""
        self.config["task_stop"]["enabled"] = False
        manager = TaskStopManager(self.config)

        task_key = GitHubIssueTaskKey("owner", "repo", 123)
        task = MockTask(task_key)
        task._assignees = []  # Bot not assigned

        result = manager.check_assignee_status(task)
        self.assertTrue(result)  # Should return True when disabled

    def test_check_assignee_status_no_bot_name(self):
        """Test that check_assignee_status returns True when bot_name not configured."""
        del self.config["github"]["bot_name"]
        manager = TaskStopManager(self.config)

        task_key = GitHubIssueTaskKey("owner", "repo", 123)
        task = MockTask(task_key)
        task._assignees = []  # Bot not assigned

        result = manager.check_assignee_status(task)
        self.assertTrue(result)  # Should return True when bot_name not configured

    def test_should_check_now_first_call(self):
        """Test that should_check_now returns True on first call."""
        result = self.manager.should_check_now()
        self.assertTrue(result)

    def test_should_check_now_interval(self):
        """Test that should_check_now respects check_interval."""
        self.config["task_stop"]["check_interval"] = 3
        self.config["task_stop"]["min_check_interval_seconds"] = 0
        manager = TaskStopManager(self.config)

        # check_interval=3 means check every 3rd call
        # Call 1: counter=1, 1%3!=0 -> False
        self.assertFalse(manager.should_check_now())
        # Call 2: counter=2, 2%3!=0 -> False
        self.assertFalse(manager.should_check_now())
        # Call 3: counter=3, 3%3==0 -> True
        self.assertTrue(manager.should_check_now())

        # Next cycle
        # Call 4: counter=4, 4%3!=0 -> False
        self.assertFalse(manager.should_check_now())
        # Call 5: counter=5, 5%3!=0 -> False
        self.assertFalse(manager.should_check_now())
        # Call 6: counter=6, 6%3==0 -> True
        self.assertTrue(manager.should_check_now())

    def test_stop_task_basic(self):
        """Test stopping a task."""
        task_key = GitHubIssueTaskKey("owner", "repo", 123)
        task = MockTask(task_key)

        # Create running context directory
        running_context_dir = self.running_dir / task.uuid
        running_context_dir.mkdir(parents=True, exist_ok=True)

        # Create some context files
        (running_context_dir / "current.jsonl").write_text('{"test": "data"}\n')

        # Stop the task
        self.manager.stop_task(task, task.uuid, llm_call_count=5)

        # Check that context directory was moved
        completed_context_dir = self.completed_dir / task.uuid
        self.assertTrue(completed_context_dir.exists())
        self.assertFalse(running_context_dir.exists())

        # Check labels
        self.assertIn("coding agent stopped", task.labels)
        self.assertNotIn("coding agent processing", task.labels)

        # Check comment
        self.assertEqual(len(task.comments), 1)
        self.assertIn("タスク停止", task.comments[0])
        self.assertIn("LLM対話回数", task.comments[0])
        self.assertIn("5", task.comments[0])

    def test_stop_task_with_planning_state(self):
        """Test stopping a task with planning state."""
        task_key = GitHubIssueTaskKey("owner", "repo", 123)
        task = MockTask(task_key)

        # Create running context directory
        running_context_dir = self.running_dir / task.uuid
        running_context_dir.mkdir(parents=True, exist_ok=True)

        planning_state = {
            "enabled": True,
            "current_phase": "execution",
            "action_counter": 3,
            "total_actions": 10,
            "revision_counter": 1,
        }

        # Stop the task
        self.manager.stop_task(task, task.uuid, planning_state=planning_state)

        # Check comment contains planning info
        self.assertEqual(len(task.comments), 1)
        self.assertIn("タスク停止", task.comments[0])
        self.assertIn("処理状況", task.comments[0])
        self.assertIn("3/10", task.comments[0])
        self.assertIn("execution", task.comments[0])

    def test_stop_task_no_running_context(self):
        """Test stopping a task when running context doesn't exist."""
        task_key = GitHubIssueTaskKey("owner", "repo", 123)
        task = MockTask(task_key)

        # Don't create running context directory

        # Stop the task (should not raise exception)
        self.manager.stop_task(task, task.uuid, llm_call_count=5)

        # Check labels were still updated
        self.assertIn("coding agent stopped", task.labels)
        self.assertNotIn("coding agent processing", task.labels)

    @patch.dict("os.environ", {"GITHUB_BOT_NAME": "env-bot-name"})
    def test_bot_name_from_env(self):
        """Test that bot name is retrieved from environment variable."""
        del self.config["github"]["bot_name"]  # Remove from config
        manager = TaskStopManager(self.config)

        task_key = GitHubIssueTaskKey("owner", "repo", 123)
        task = MockTask(task_key)
        task._assignees = ["env-bot-name"]

        result = manager.check_assignee_status(task)
        self.assertTrue(result)

    def test_check_assignee_status_api_error(self):
        """Test that API errors don't stop the task."""
        task_key = GitHubIssueTaskKey("owner", "repo", 123)
        task = MockTask(task_key)

        # Mock refresh_assignees to raise an exception
        task.refresh_assignees = MagicMock(side_effect=Exception("API Error"))

        # Should return True (continue processing) on error
        result = self.manager.check_assignee_status(task)
        self.assertTrue(result)


class TestTaskStopManagerGitLab(unittest.TestCase):
    """Test TaskStopManager with GitLab tasks."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.config = {
            "task_stop": {
                "enabled": True,
                "check_interval": 1,
                "min_check_interval_seconds": 0,
            },
            "context_storage": {
                "base_dir": str(self.temp_dir / "contexts"),
            },
            "gitlab": {
                "processing_label": "coding agent processing",
                "stopped_label": "coding agent stopped",
                "bot_name": "gitlab-bot",
            },
        }
        self.manager = TaskStopManager(self.config)

    def tearDown(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_gitlab_bot_name_from_config(self):
        """Test that GitLab bot name is retrieved from config."""
        from handlers.task_key import GitLabIssueTaskKey

        # 環境変数をクリアして設定ファイルからの読み込みを確実にする
        with patch.dict("os.environ", {}, clear=False):
            # GITLAB_BOT_NAMEが設定されている場合は削除
            if "GITLAB_BOT_NAME" in os.environ:
                del os.environ["GITLAB_BOT_NAME"]

            class MockGitLabTask:
                def __init__(self):
                    self.uuid = "test-uuid"
                    self._assignees = ["gitlab-bot"]

                def get_task_key(self):
                    return GitLabIssueTaskKey(123, 1)

                def refresh_assignees(self):
                    return self._assignees

            task = MockGitLabTask()
            result = self.manager.check_assignee_status(task)
            self.assertTrue(result)

    @patch.dict("os.environ", {"GITLAB_BOT_NAME": "env-gitlab-bot"})
    def test_gitlab_bot_name_from_env(self):
        """Test that GitLab bot name is retrieved from environment variable."""
        from handlers.task_key import GitLabIssueTaskKey
        del self.config["gitlab"]["bot_name"]
        manager = TaskStopManager(self.config)

        class MockGitLabTask:
            def __init__(self):
                self.uuid = "test-uuid"
                self._assignees = ["env-gitlab-bot"]

            def get_task_key(self):
                return GitLabIssueTaskKey(123, 1)

            def refresh_assignees(self):
                return self._assignees

        task = MockGitLabTask()
        result = manager.check_assignee_status(task)
        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()
