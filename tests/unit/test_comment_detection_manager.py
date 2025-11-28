"""Unit tests for comment detection functionality."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from handlers.task_key import GitHubIssueTaskKey


class MockTask:
    """Mock task for testing."""

    def __init__(self, task_key: GitHubIssueTaskKey, number: int = 1) -> None:
        """Initialize mock task."""
        self.uuid = "test-uuid-123"
        self.user = "testuser"
        self._task_key = task_key
        self.number = number
        self.is_resumed = False
        self._comments: list[dict[str, Any]] = []

    def get_task_key(self) -> GitHubIssueTaskKey:
        """Get task key."""
        return self._task_key

    def get_comments(self) -> list[dict[str, Any]]:
        """Get comments."""
        return self._comments

    def set_comments(self, comments: list[dict[str, Any]]) -> None:
        """Set comments for testing."""
        self._comments = comments


class MockLLMClient:
    """Mock LLM client for testing."""

    def __init__(self) -> None:
        """Initialize mock LLM client."""
        self.messages: list[str] = []

    def send_user_message(self, message: str) -> None:
        """Record user message."""
        self.messages.append(message)


class TestCommentDetectionManager(unittest.TestCase):
    """Test CommentDetectionManager functionality."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.task_key = GitHubIssueTaskKey("owner", "repo", 123)
        self.task = MockTask(self.task_key)

        # Config with bot_name set
        self.config = {
            "github": {
                "bot_name": "coding-agent-bot",
                "processing_label": "coding agent processing",
            },
            "context_storage": {
                "base_dir": str(self.temp_dir / "contexts"),
            },
        }

    def tearDown(self) -> None:
        """Clean up test fixtures."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_initialization_with_bot_name(self) -> None:
        """Test that manager is enabled when bot_name is set."""
        from comment_detection_manager import CommentDetectionManager

        manager = CommentDetectionManager(self.task, self.config)
        self.assertTrue(manager.enabled)
        self.assertEqual(manager.bot_username, "coding-agent-bot")

    def test_initialization_without_bot_name(self) -> None:
        """Test that manager is disabled when bot_name is not set."""
        from comment_detection_manager import CommentDetectionManager

        config = {"github": {}}
        manager = CommentDetectionManager(self.task, config)
        self.assertFalse(manager.enabled)
        self.assertIsNone(manager.bot_username)

    def test_initialize_records_existing_comments(self) -> None:
        """Test that initialize() records existing comment IDs."""
        from comment_detection_manager import CommentDetectionManager

        # Set up existing comments
        self.task.set_comments(
            [
                {"id": 1, "author": "user1", "body": "comment 1", "created_at": "2024-01-01T00:00:00Z"},
                {"id": 2, "author": "user2", "body": "comment 2", "created_at": "2024-01-02T00:00:00Z"},
            ]
        )

        manager = CommentDetectionManager(self.task, self.config)
        manager.initialize()

        self.assertEqual(manager.last_comment_ids, {"1", "2"})
        self.assertIsNotNone(manager.last_check_time)

    def test_check_for_new_comments_detects_new(self) -> None:
        """Test that new comments are detected."""
        from comment_detection_manager import CommentDetectionManager

        # Initialize with existing comments
        self.task.set_comments(
            [
                {"id": 1, "author": "user1", "body": "comment 1", "created_at": "2024-01-01T00:00:00Z"},
            ]
        )

        manager = CommentDetectionManager(self.task, self.config)
        manager.initialize()

        # Add new comment
        self.task.set_comments(
            [
                {"id": 1, "author": "user1", "body": "comment 1", "created_at": "2024-01-01T00:00:00Z"},
                {"id": 2, "author": "user2", "body": "new comment", "created_at": "2024-01-02T00:00:00Z"},
            ]
        )

        new_comments = manager.check_for_new_comments()
        self.assertEqual(len(new_comments), 1)
        self.assertEqual(new_comments[0]["id"], 2)

    def test_check_for_new_comments_filters_bot_comments(self) -> None:
        """Test that bot's own comments are filtered out."""
        from comment_detection_manager import CommentDetectionManager

        # Initialize with existing comments
        self.task.set_comments(
            [
                {"id": 1, "author": "user1", "body": "comment 1", "created_at": "2024-01-01T00:00:00Z"},
            ]
        )

        manager = CommentDetectionManager(self.task, self.config)
        manager.initialize()

        # Add new comments including one from bot
        self.task.set_comments(
            [
                {"id": 1, "author": "user1", "body": "comment 1", "created_at": "2024-01-01T00:00:00Z"},
                {"id": 2, "author": "coding-agent-bot", "body": "bot comment", "created_at": "2024-01-02T00:00:00Z"},
                {"id": 3, "author": "user2", "body": "user comment", "created_at": "2024-01-03T00:00:00Z"},
            ]
        )

        new_comments = manager.check_for_new_comments()
        self.assertEqual(len(new_comments), 1)
        self.assertEqual(new_comments[0]["author"], "user2")

    def test_check_for_new_comments_returns_empty_when_no_new(self) -> None:
        """Test that empty list is returned when no new comments."""
        from comment_detection_manager import CommentDetectionManager

        # Initialize with existing comments
        self.task.set_comments(
            [
                {"id": 1, "author": "user1", "body": "comment 1", "created_at": "2024-01-01T00:00:00Z"},
            ]
        )

        manager = CommentDetectionManager(self.task, self.config)
        manager.initialize()

        # No changes
        new_comments = manager.check_for_new_comments()
        self.assertEqual(len(new_comments), 0)

    def test_check_for_new_comments_disabled(self) -> None:
        """Test that disabled manager returns empty list."""
        from comment_detection_manager import CommentDetectionManager

        config = {"github": {}}  # No bot_name
        manager = CommentDetectionManager(self.task, config)

        new_comments = manager.check_for_new_comments()
        self.assertEqual(len(new_comments), 0)

    def test_format_comment_message_single(self) -> None:
        """Test formatting a single comment."""
        from comment_detection_manager import CommentDetectionManager

        manager = CommentDetectionManager(self.task, self.config)

        comments = [
            {"id": 1, "author": "user1", "body": "Hello world", "created_at": "2024-01-01T00:00:00Z"},
        ]

        message = manager.format_comment_message(comments)
        self.assertIn("@user1", message)
        self.assertIn("Hello world", message)
        self.assertIn("[New Comment from", message)

    def test_format_comment_message_multiple(self) -> None:
        """Test formatting multiple comments."""
        from comment_detection_manager import CommentDetectionManager

        manager = CommentDetectionManager(self.task, self.config)

        comments = [
            {"id": 1, "author": "user1", "body": "First comment", "created_at": "2024-01-01T00:00:00Z"},
            {"id": 2, "author": "user2", "body": "Second comment", "created_at": "2024-01-02T00:00:00Z"},
        ]

        message = manager.format_comment_message(comments)
        self.assertIn("[New Comments Detected]", message)
        self.assertIn("Comment 1 from @user1", message)
        self.assertIn("Comment 2 from @user2", message)
        self.assertIn("First comment", message)
        self.assertIn("Second comment", message)

    def test_format_comment_message_empty(self) -> None:
        """Test formatting empty comment list."""
        from comment_detection_manager import CommentDetectionManager

        manager = CommentDetectionManager(self.task, self.config)

        message = manager.format_comment_message([])
        self.assertEqual(message, "")

    def test_add_to_context(self) -> None:
        """Test adding comments to LLM context."""
        from comment_detection_manager import CommentDetectionManager

        manager = CommentDetectionManager(self.task, self.config)
        llm_client = MockLLMClient()

        comments = [
            {"id": 1, "author": "user1", "body": "Test comment", "created_at": "2024-01-01T00:00:00Z"},
        ]

        manager.add_to_context(llm_client, comments)

        self.assertEqual(len(llm_client.messages), 1)
        self.assertIn("Test comment", llm_client.messages[0])

    def test_add_to_context_empty_list(self) -> None:
        """Test that empty list doesn't add to context."""
        from comment_detection_manager import CommentDetectionManager

        manager = CommentDetectionManager(self.task, self.config)
        llm_client = MockLLMClient()

        manager.add_to_context(llm_client, [])

        self.assertEqual(len(llm_client.messages), 0)

    def test_is_bot_comment(self) -> None:
        """Test bot comment detection."""
        from comment_detection_manager import CommentDetectionManager

        manager = CommentDetectionManager(self.task, self.config)

        bot_comment = {"author": "coding-agent-bot"}
        user_comment = {"author": "regular-user"}

        self.assertTrue(manager.is_bot_comment(bot_comment))
        self.assertFalse(manager.is_bot_comment(user_comment))

    def test_get_state(self) -> None:
        """Test state serialization for pause."""
        from comment_detection_manager import CommentDetectionManager

        # Initialize with existing comments
        self.task.set_comments(
            [
                {"id": 1, "author": "user1", "body": "comment 1", "created_at": "2024-01-01T00:00:00Z"},
                {"id": 2, "author": "user2", "body": "comment 2", "created_at": "2024-01-02T00:00:00Z"},
            ]
        )

        manager = CommentDetectionManager(self.task, self.config)
        manager.initialize()

        state = manager.get_state()

        self.assertIn("last_comment_ids", state)
        self.assertIn("last_check_timestamp", state)
        self.assertEqual(set(state["last_comment_ids"]), {"1", "2"})
        self.assertIsNotNone(state["last_check_timestamp"])

    def test_restore_state(self) -> None:
        """Test state restoration for resume."""
        from comment_detection_manager import CommentDetectionManager

        manager = CommentDetectionManager(self.task, self.config)

        state = {
            "last_comment_ids": ["1", "2", "3"],
            "last_check_timestamp": "2024-01-01T00:00:00+00:00",
        }

        manager.restore_state(state)

        self.assertEqual(manager.last_comment_ids, {"1", "2", "3"})
        self.assertIsNotNone(manager.last_check_time)

    def test_restore_state_empty(self) -> None:
        """Test that empty state doesn't crash."""
        from comment_detection_manager import CommentDetectionManager

        manager = CommentDetectionManager(self.task, self.config)

        # Should not raise
        manager.restore_state({})
        manager.restore_state(None)

    def test_comment_detection_round_trip(self) -> None:
        """Test full round trip: initialize, detect, save, restore, detect."""
        from comment_detection_manager import CommentDetectionManager

        # Initialize with comments
        self.task.set_comments(
            [
                {"id": 1, "author": "user1", "body": "comment 1", "created_at": "2024-01-01T00:00:00Z"},
            ]
        )

        manager1 = CommentDetectionManager(self.task, self.config)
        manager1.initialize()

        # Add new comment
        self.task.set_comments(
            [
                {"id": 1, "author": "user1", "body": "comment 1", "created_at": "2024-01-01T00:00:00Z"},
                {"id": 2, "author": "user2", "body": "comment 2", "created_at": "2024-01-02T00:00:00Z"},
            ]
        )

        # Detect new comment
        new_comments = manager1.check_for_new_comments()
        self.assertEqual(len(new_comments), 1)

        # Save state
        state = manager1.get_state()

        # Create new manager and restore
        manager2 = CommentDetectionManager(self.task, self.config)
        manager2.restore_state(state)

        # No new comments should be detected
        new_comments = manager2.check_for_new_comments()
        self.assertEqual(len(new_comments), 0)

        # Add another comment
        self.task.set_comments(
            [
                {"id": 1, "author": "user1", "body": "comment 1", "created_at": "2024-01-01T00:00:00Z"},
                {"id": 2, "author": "user2", "body": "comment 2", "created_at": "2024-01-02T00:00:00Z"},
                {"id": 3, "author": "user3", "body": "comment 3", "created_at": "2024-01-03T00:00:00Z"},
            ]
        )

        # Should detect the new comment
        new_comments = manager2.check_for_new_comments()
        self.assertEqual(len(new_comments), 1)
        self.assertEqual(new_comments[0]["id"], 3)


class MockGitLabTask:
    """Mock GitLab task for testing."""

    def __init__(self, task_key: Any, number: int = 1) -> None:
        """Initialize mock GitLab task."""
        self.uuid = "test-uuid-123"
        self.user = "testuser"
        self._task_key = task_key
        self.number = number
        self.is_resumed = False
        self._comments: list[dict[str, Any]] = []

    def get_task_key(self) -> Any:
        """Get task key."""
        return self._task_key

    def get_comments(self) -> list[dict[str, Any]]:
        """Get comments."""
        return self._comments

    def set_comments(self, comments: list[dict[str, Any]]) -> None:
        """Set comments for testing."""
        self._comments = comments


class TestCommentDetectionManagerGitLab(unittest.TestCase):
    """Test CommentDetectionManager with GitLab task type."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        from handlers.task_key import GitLabIssueTaskKey

        self.temp_dir = Path(tempfile.mkdtemp())
        self.task_key = GitLabIssueTaskKey(123, 456)
        self.task = MockGitLabTask(self.task_key)

        # Config with GitLab bot_name set
        self.config = {
            "gitlab": {
                "bot_name": "gitlab-bot",
                "processing_label": "coding agent processing",
            },
        }

    def tearDown(self) -> None:
        """Clean up test fixtures."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_gitlab_initialization_with_bot_name(self) -> None:
        """Test that manager is enabled for GitLab when bot_name is set."""
        import os
        from unittest.mock import patch
        from comment_detection_manager import CommentDetectionManager

        # 環境変数の影響を排除するためにモック
        with patch.dict(os.environ, {}, clear=True):
            manager = CommentDetectionManager(self.task, self.config)
            self.assertTrue(manager.enabled)
            self.assertEqual(manager.bot_username, "gitlab-bot")


if __name__ == "__main__":
    unittest.main()
