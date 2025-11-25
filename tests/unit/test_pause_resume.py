"""Unit tests for pause/resume functionality."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from handlers.task_key import GitHubIssueTaskKey
from pause_resume_manager import PauseResumeManager


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


class TestPauseResumeManager(unittest.TestCase):
    """Test PauseResumeManager functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.config = {
            "pause_resume": {
                "enabled": True,
                "signal_file": str(self.temp_dir / "pause_signal"),
                "check_interval": 1,
                "paused_task_expiry_days": 30,
                "paused_dir": "contexts/paused",
            },
            "context_storage": {
                "base_dir": str(self.temp_dir / "contexts"),
            },
            "github": {
                "processing_label": "coding agent processing",
                "paused_label": "coding agent paused",
            },
        }
        self.manager = PauseResumeManager(self.config)

        # Create contexts directories
        self.contexts_dir = self.temp_dir / "contexts"
        self.running_dir = self.contexts_dir / "running"
        self.paused_dir = self.contexts_dir / "paused"
        self.running_dir.mkdir(parents=True, exist_ok=True)
        self.paused_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_check_pause_signal_no_file(self):
        """Test pause signal check when file doesn't exist."""
        result = self.manager.check_pause_signal()
        self.assertFalse(result)

    def test_check_pause_signal_file_exists(self):
        """Test pause signal check when file exists."""
        signal_file = Path(self.config["pause_resume"]["signal_file"])
        signal_file.parent.mkdir(parents=True, exist_ok=True)
        signal_file.touch()

        result = self.manager.check_pause_signal()
        self.assertTrue(result)

    def test_pause_task_basic(self):
        """Test pausing a task."""
        task_key = GitHubIssueTaskKey("owner", "repo", 123)
        task = MockTask(task_key)

        # Create running context directory
        running_context_dir = self.running_dir / task.uuid
        running_context_dir.mkdir(parents=True, exist_ok=True)

        # Create some context files
        (running_context_dir / "current.jsonl").write_text('{"test": "data"}\n')

        # Pause the task
        self.manager.pause_task(task, task.uuid, planning_state=None)

        # Check that context directory was moved
        paused_context_dir = self.paused_dir / task.uuid
        self.assertTrue(paused_context_dir.exists())
        self.assertFalse(running_context_dir.exists())

        # Check task_state.json
        task_state_path = paused_context_dir / "task_state.json"
        self.assertTrue(task_state_path.exists())

        with task_state_path.open() as f:
            task_state = json.load(f)

        self.assertEqual(task_state["uuid"], task.uuid)
        self.assertEqual(task_state["user"], task.user)
        self.assertEqual(task_state["status"], "paused")
        self.assertEqual(task_state["resume_count"], 0)

        # Check labels
        self.assertIn("coding agent paused", task.labels)
        self.assertNotIn("coding agent processing", task.labels)

        # Check comment
        self.assertEqual(len(task.comments), 1)
        self.assertIn("一時停止", task.comments[0])

    def test_pause_task_with_planning_state(self):
        """Test pausing a task with planning state."""
        task_key = GitHubIssueTaskKey("owner", "repo", 123)
        task = MockTask(task_key)

        # Create running context directory
        running_context_dir = self.running_dir / task.uuid
        running_context_dir.mkdir(parents=True, exist_ok=True)

        planning_state = {
            "enabled": True,
            "current_phase": "execution",
            "action_counter": 3,
            "revision_counter": 1,
            "checklist_comment_id": 12345,
        }

        # Pause the task
        self.manager.pause_task(task, task.uuid, planning_state=planning_state)

        # Check task_state.json contains planning state
        paused_context_dir = self.paused_dir / task.uuid
        task_state_path = paused_context_dir / "task_state.json"

        with task_state_path.open() as f:
            task_state = json.load(f)

        self.assertEqual(task_state["planning_state"], planning_state)

    def test_get_paused_tasks(self):
        """Test getting list of paused tasks."""
        # Create a paused task
        task_uuid = "test-uuid-456"
        paused_context_dir = self.paused_dir / task_uuid
        paused_context_dir.mkdir(parents=True, exist_ok=True)

        task_state = {
            "task_key": {
                "task_type": "github_issue",
                "owner": "owner",
                "repo": "repo",
                "number": 123,
            },
            "uuid": task_uuid,
            "user": "testuser",
            "status": "paused",
        }

        task_state_path = paused_context_dir / "task_state.json"
        with task_state_path.open("w") as f:
            json.dump(task_state, f)

        # Get paused tasks
        paused_tasks = self.manager.get_paused_tasks()

        self.assertEqual(len(paused_tasks), 1)
        self.assertEqual(paused_tasks[0]["uuid"], task_uuid)
        self.assertEqual(paused_tasks[0]["status"], "paused")

    def test_prepare_resume_task_dict(self):
        """Test preparing task dictionary for resume."""
        task_state = {
            "task_key": {
                "task_type": "github_issue",
                "owner": "owner",
                "repo": "repo",
                "number": 123,
            },
            "uuid": "test-uuid-789",
            "user": "testuser",
            "status": "paused",
            "context_path": "contexts/paused/test-uuid-789",
        }

        task_dict = self.manager.prepare_resume_task_dict(task_state)

        self.assertEqual(task_dict["task_type"], "github_issue")
        self.assertEqual(task_dict["uuid"], "test-uuid-789")
        self.assertEqual(task_dict["user"], "testuser")
        self.assertTrue(task_dict["is_resumed"])
        self.assertEqual(task_dict["paused_context_path"], "contexts/paused/test-uuid-789")

    def test_restore_task_context(self):
        """Test restoring task context from paused state."""
        task_key = GitHubIssueTaskKey("owner", "repo", 123)
        task = MockTask(task_key)

        # Create paused context directory
        paused_context_dir = self.paused_dir / task.uuid
        paused_context_dir.mkdir(parents=True, exist_ok=True)

        # Create task_state.json
        task_state = {
            "task_key": task_key.to_dict(),
            "uuid": task.uuid,
            "user": task.user,
            "status": "paused",
            "resume_count": 0,
            "planning_state": {
                "enabled": True,
                "current_phase": "execution",
                "action_counter": 2,
            },
        }

        task_state_path = paused_context_dir / "task_state.json"
        with task_state_path.open("w") as f:
            json.dump(task_state, f)

        # Create some context files
        (paused_context_dir / "current.jsonl").write_text('{"test": "data"}\n')

        # Restore task context
        planning_state = self.manager.restore_task_context(task, task.uuid)

        # Check that context directory was moved
        running_context_dir = self.running_dir / task.uuid
        self.assertTrue(running_context_dir.exists())
        self.assertFalse(paused_context_dir.exists())

        # Check planning state was returned
        self.assertIsNotNone(planning_state)
        self.assertEqual(planning_state["current_phase"], "execution")
        self.assertEqual(planning_state["action_counter"], 2)

        # Check labels
        self.assertIn("coding agent processing", task.labels)

        # Check comment
        self.assertTrue(len(task.comments) > 0)

    def test_pause_signal_disabled(self):
        """Test that pause signal is ignored when disabled."""
        self.config["pause_resume"]["enabled"] = False
        manager = PauseResumeManager(self.config)

        signal_file = Path(self.config["pause_resume"]["signal_file"])
        signal_file.parent.mkdir(parents=True, exist_ok=True)
        signal_file.touch()

        result = manager.check_pause_signal()
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
