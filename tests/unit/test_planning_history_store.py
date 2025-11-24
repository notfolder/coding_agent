"""Unit tests for PlanningHistoryStore."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from handlers.planning_history_store import PlanningHistoryStore


class TestPlanningHistoryStore(unittest.TestCase):
    """Test PlanningHistoryStore functionality."""

    def setUp(self) -> None:
        """Set up test environment."""
        # Create temporary directory for test files
        self.temp_dir = tempfile.mkdtemp()
        self.config = {
            "history": {
                "storage_type": "jsonl",
                "directory": self.temp_dir,
            }
        }
        self.task_uuid = "test-uuid-12345"
        self.store = PlanningHistoryStore(self.task_uuid, self.config)

    def tearDown(self) -> None:
        """Clean up test environment."""
        # Remove test files
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_store_creation(self) -> None:
        """Test PlanningHistoryStore object creation."""
        assert self.store.task_uuid == self.task_uuid
        assert self.store.directory == Path(self.temp_dir)
        assert self.store.filepath == Path(self.temp_dir) / f"{self.task_uuid}.jsonl"

    def test_save_and_load_plan(self) -> None:
        """Test saving and loading a plan."""
        plan = {
            "goal_understanding": {
                "main_objective": "Test objective",
                "success_criteria": ["Criterion 1", "Criterion 2"],
                "constraints": ["Constraint 1"],
            },
            "task_decomposition": {
                "reasoning": "Test reasoning",
                "subtasks": [
                    {
                        "id": "task_1",
                        "description": "First task",
                        "dependencies": [],
                        "estimated_complexity": "low",
                    }
                ],
            },
            "action_plan": {
                "execution_order": ["task_1"],
                "actions": [],
            },
        }

        # Save plan
        self.store.save_plan(plan)

        # Check file exists
        assert self.store.filepath.exists()

        # Load plan
        loaded_entry = self.store.get_latest_plan()
        assert loaded_entry is not None
        assert loaded_entry["type"] == "plan"
        assert loaded_entry["plan"] == plan
        assert "timestamp" in loaded_entry

    def test_has_plan(self) -> None:
        """Test checking if plan exists."""
        # Initially no plan
        assert not self.store.has_plan()

        # Save a plan
        plan = {"goal": "test"}
        self.store.save_plan(plan)

        # Now plan exists
        assert self.store.has_plan()

    def test_save_reflection(self) -> None:
        """Test saving reflection."""
        reflection = {
            "action_evaluated": "test_action",
            "status": "success",
            "evaluation": "Action completed successfully",
            "plan_revision_needed": False,
        }

        self.store.save_reflection(reflection)

        # Check file exists
        assert self.store.filepath.exists()

        # Get all reflections
        reflections = self.store.get_all_reflections()
        assert len(reflections) == 1
        assert reflections[0]["type"] == "reflection"
        assert reflections[0]["evaluation"] == reflection

    def test_save_revision(self) -> None:
        """Test saving plan revision."""
        revised_plan = {
            "action_plan": {
                "execution_order": ["task_1", "task_2"],
                "actions": [],
            }
        }

        reflection = {
            "reason": "Error occurred",
            "changes": ["Added task_2"],
        }

        self.store.save_revision(revised_plan, reflection)

        # Check file exists
        assert self.store.filepath.exists()

        # Get revision history
        revisions = self.store.get_revision_history()
        assert len(revisions) == 1
        assert revisions[0]["type"] == "revision"
        assert revisions[0]["updated_plan"] == revised_plan
        assert revisions[0]["reason"] == "Error occurred"

    def test_get_latest_plan_with_revision(self) -> None:
        """Test getting latest plan when revisions exist."""
        # Save initial plan
        plan1 = {"version": 1}
        self.store.save_plan(plan1)

        # Save a reflection
        reflection = {"status": "error", "reason": "Test error", "changes": ["Change 1"]}
        self.store.save_reflection(reflection)

        # Save revision
        plan2 = {"version": 2}
        self.store.save_revision(plan2, reflection)

        # Get latest plan should return the revision
        latest = self.store.get_latest_plan()
        assert latest is not None
        assert latest["type"] == "revision"
        assert latest["updated_plan"] == plan2

    def test_multiple_reflections(self) -> None:
        """Test saving and retrieving multiple reflections."""
        # Save multiple reflections
        for i in range(3):
            reflection = {
                "action": f"action_{i}",
                "status": "success",
            }
            self.store.save_reflection(reflection)

        # Get all reflections
        reflections = self.store.get_all_reflections()
        assert len(reflections) == 3

    def test_empty_file_handling(self) -> None:
        """Test handling of non-existent files."""
        # Before any save, file doesn't exist
        assert not self.store.filepath.exists()

        # Get latest plan should return None
        assert self.store.get_latest_plan() is None

        # Get reflections should return empty list
        assert self.store.get_all_reflections() == []

        # Get revisions should return empty list
        assert self.store.get_revision_history() == []

    def test_jsonl_format(self) -> None:
        """Test that entries are saved in valid JSONL format."""
        # Save a plan
        plan = {"test": "data"}
        self.store.save_plan(plan)

        # Save a reflection
        reflection = {"status": "success"}
        self.store.save_reflection(reflection)

        # Read file and verify it's valid JSONL
        with self.store.filepath.open("r") as f:
            lines = f.readlines()
        
        assert len(lines) == 2
        
        # Each line should be valid JSON
        for line in lines:
            data = json.loads(line.strip())
            assert "type" in data
            assert "timestamp" in data


if __name__ == "__main__":
    unittest.main()
