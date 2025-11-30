"""Unit tests for context storage classes."""

from __future__ import annotations

import json
import tempfile
import unittest
import unittest.mock
from pathlib import Path

# Import context storage classes
from context_storage import (
    ContextCompressor,
    MessageStore,
    SummaryStore,
    TaskContextManager,
    ToolStore,
)
from handlers.task_key import GitHubIssueTaskKey


class TestMessageStore(unittest.TestCase):
    """Test MessageStore functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.config = {
            "llm": {
                "provider": "openai",
                "openai": {
                    "context_length": 128000,
                },
            },
        }
        self.store = MessageStore(self.temp_dir, self.config)

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_add_message(self):
        """Test adding a message."""
        seq = self.store.add_message("system", "Test system prompt")
        self.assertEqual(seq, 1)

        # Check messages.jsonl
        with self.store.messages_file.open() as f:
            line = f.readline()
            msg = json.loads(line)
            self.assertEqual(msg["role"], "system")
            self.assertEqual(msg["content"], "Test system prompt")
            self.assertEqual(msg["seq"], 1)

        # Check current.jsonl
        with self.store.current_file.open() as f:
            line = f.readline()
            msg = json.loads(line)
            self.assertEqual(msg["role"], "system")
            self.assertEqual(msg["content"], "Test system prompt")

    def test_add_multiple_messages(self):
        """Test adding multiple messages."""
        self.store.add_message("system", "System prompt")
        self.store.add_message("user", "User message")
        self.store.add_message("assistant", "Assistant response")

        count = self.store.count_messages()
        self.assertEqual(count, 3)

    def test_get_current_token_count(self):
        """Test token count calculation."""
        self.store.add_message("system", "1234")  # 1 token
        self.store.add_message("user", "12345678")  # 2 tokens

        tokens = self.store.get_current_token_count()
        self.assertEqual(tokens, 3)

    def test_recreate_current_context(self):
        """Test recreating current context with summary."""
        # Add some messages
        self.store.add_message("system", "System")
        self.store.add_message("user", "Message 1")
        self.store.add_message("assistant", "Response 1")

        # Create unsummarized file
        unsummarized_file = self.temp_dir / "unsummarized.jsonl"
        with unsummarized_file.open("w") as f:
            f.write(json.dumps({"role": "user", "content": "Recent message"}) + "\n")

        # Recreate context
        self.store.recreate_current_context("Summary text", 100, unsummarized_file)

        # Check current.jsonl
        messages = []
        with self.store.current_file.open() as f:
            for line in f:
                messages.append(json.loads(line))

        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["role"], "assistant")
        self.assertEqual(messages[0]["content"], "Summary text")
        self.assertEqual(messages[1]["role"], "user")
        self.assertEqual(messages[1]["content"], "Recent message")


class TestSummaryStore(unittest.TestCase):
    """Test SummaryStore functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.store = SummaryStore(self.temp_dir)

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_add_summary(self):
        """Test adding a summary."""
        summary_id = self.store.add_summary(
            start_seq=1,
            end_seq=10,
            summary_text="Test summary",
            original_tokens=1000,
            summary_tokens=100,
        )
        self.assertEqual(summary_id, 1)

        # Check summaries.jsonl
        with self.store.summaries_file.open() as f:
            line = f.readline()
            summary = json.loads(line)
            self.assertEqual(summary["id"], 1)
            self.assertEqual(summary["summary"], "Test summary")
            self.assertEqual(summary["ratio"], 0.1)

    def test_get_latest_summary(self):
        """Test getting latest summary."""
        self.store.add_summary(1, 10, "Summary 1", 1000, 100)
        self.store.add_summary(11, 20, "Summary 2", 1000, 150)

        latest = self.store.get_latest_summary()
        self.assertEqual(latest["id"], 2)
        self.assertEqual(latest["summary"], "Summary 2")

    def test_count_summaries(self):
        """Test counting summaries."""
        self.store.add_summary(1, 10, "Summary 1", 1000, 100)
        self.store.add_summary(11, 20, "Summary 2", 1000, 150)

        count = self.store.count_summaries()
        self.assertEqual(count, 2)


class TestToolStore(unittest.TestCase):
    """Test ToolStore functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.store = ToolStore(self.temp_dir)

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_add_tool_call_success(self):
        """Test recording successful tool call."""
        seq = self.store.add_tool_call(
            tool_name="github_get_file",
            args={"path": "test.py"},
            result={"content": "file content"},
            status="success",
            duration_ms=123.45,
        )
        self.assertEqual(seq, 1)

        # Check tools.jsonl
        with self.store.tools_file.open() as f:
            line = f.readline()
            call = json.loads(line)
            self.assertEqual(call["tool"], "github_get_file")
            self.assertEqual(call["status"], "success")

    def test_add_tool_call_error(self):
        """Test recording failed tool call."""
        seq = self.store.add_tool_call(
            tool_name="github_get_file",
            args={"path": "test.py"},
            result=None,
            status="error",
            duration_ms=50.0,
            error="File not found",
        )
        self.assertEqual(seq, 1)

        # Check tools.jsonl
        with self.store.tools_file.open() as f:
            line = f.readline()
            call = json.loads(line)
            self.assertEqual(call["status"], "error")
            self.assertEqual(call["error"], "File not found")


class TestTaskContextManager(unittest.TestCase):
    """Test TaskContextManager functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.config = {
            "llm": {
                "provider": "openai",
                "openai": {
                    "model": "gpt-4o",
                    "context_length": 128000,
                },
            },
            "context_storage": {
                "base_dir": str(self.temp_dir / "contexts"),
                "compression_threshold": 0.7,
            },
            "database": {
                "host": "localhost",
                "port": 5432,
                "name": "test_db",
                "user": "test",
                "password": "test",
            },
        }
        self.task_key = GitHubIssueTaskKey("owner", "repo", 123)
        
        # TaskDBManagerをモック化
        self.mock_db_manager_patcher = unittest.mock.patch(
            "context_storage.task_context_manager.TaskDBManager"
        )
        self.mock_db_manager_class = self.mock_db_manager_patcher.start()
        
        # モックDBTaskを設定
        self.mock_db_task = unittest.mock.MagicMock()
        self.mock_db_task.uuid = "test-uuid-123"
        self.mock_db_task.status = "running"
        self.mock_db_task.llm_call_count = 0
        self.mock_db_task.tool_call_count = 0
        self.mock_db_task.total_tokens = 0
        self.mock_db_task.compression_count = 0
        
        # TaskDBManagerインスタンスのメソッドをモック化
        self.mock_db_manager = self.mock_db_manager_class.return_value
        self.mock_db_manager.create_task.return_value = self.mock_db_task
        self.mock_db_manager.get_task.return_value = self.mock_db_task
        self.mock_db_manager.save_task.return_value = self.mock_db_task

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        self.mock_db_manager_patcher.stop()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_initialization(self):
        """Test TaskContextManager initialization."""
        manager = TaskContextManager(
            task_key=self.task_key,
            task_uuid="test-uuid-123",
            config=self.config,
            user="testuser",
        )

        # Check directory structure
        self.assertTrue(manager.context_dir.exists())
        self.assertTrue((manager.context_dir / "metadata.json").exists())

        # Check that TaskDBManager.create_task was called
        self.mock_db_manager.create_task.assert_called_once()

    def test_update_statistics(self):
        """Test updating statistics."""
        manager = TaskContextManager(
            task_key=self.task_key,
            task_uuid="test-uuid-123",
            config=self.config,
        )

        manager.update_statistics(llm_calls=1, tool_calls=2, tokens=1000)

        # Check that save_task was called (statistics update)
        # Note: create_task is called during __init__, and save_task during update_statistics
        self.mock_db_manager.save_task.assert_called()

    def test_complete(self):
        """Test completing a task."""
        manager = TaskContextManager(
            task_key=self.task_key,
            task_uuid="test-uuid-123",
            config=self.config,
        )

        manager.complete()

        # Check that save_task was called with completed status
        self.mock_db_manager.save_task.assert_called()
        
        # Check directory moved
        completed_dir = manager.completed_dir / "test-uuid-123"
        self.assertTrue(completed_dir.exists())


if __name__ == "__main__":
    unittest.main()
