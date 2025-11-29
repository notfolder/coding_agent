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
        self.temp_dir = Path(tempfile.mkdtemp())
        self.planning_dir = self.temp_dir / "planning"
        self.planning_dir.mkdir(parents=True, exist_ok=True)
        self.task_uuid = "test-uuid-12345"
        self.store = PlanningHistoryStore(self.task_uuid, self.planning_dir)

    def tearDown(self) -> None:
        """Clean up test environment."""
        # Remove test files
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_store_creation(self) -> None:
        """Test PlanningHistoryStore object creation."""
        assert self.store.task_uuid == self.task_uuid
        assert self.store.directory == self.planning_dir
        assert self.store.filepath == self.planning_dir / f"{self.task_uuid}.jsonl"

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

    def test_save_and_get_verification(self) -> None:
        """Test saving and retrieving verification results."""
        # 検証結果を保存
        verification_result = {
            "verification_passed": True,
            "issues_found": [],
            "placeholder_detected": {"count": 0, "locations": []},
            "additional_work_needed": False,
            "additional_actions": [],
            "completion_confidence": 0.95,
            "comment": "All implementations are complete.",
        }

        self.store.save_verification(verification_result)

        # ファイルが存在することを確認
        assert self.store.filepath.exists()

        # JSONLファイルを読み込んで検証
        entries = self.store._read_jsonl()
        verification_entries = [e for e in entries if e.get("type") == "verification"]

        assert len(verification_entries) == 1
        assert verification_entries[0]["verification_result"] == verification_result
        assert "timestamp" in verification_entries[0]
        assert verification_entries[0]["task_uuid"] == self.task_uuid

    def test_save_multiple_verifications(self) -> None:
        """Test saving multiple verification results (for multiple rounds)."""
        # 複数ラウンドの検証結果を保存
        for i in range(3):
            verification_result = {
                "verification_passed": i == 2,  # 3回目のみ成功
                "issues_found": [] if i == 2 else [f"Issue {i}"],
                "completion_confidence": 0.5 + i * 0.2,
            }
            self.store.save_verification(verification_result)

        # JSONLファイルを読み込んで検証
        entries = self.store._read_jsonl()
        verification_entries = [e for e in entries if e.get("type") == "verification"]

        assert len(verification_entries) == 3
        
        # 最後の検証結果のみ成功
        assert verification_entries[0]["verification_result"]["verification_passed"] is False
        assert verification_entries[1]["verification_result"]["verification_passed"] is False
        assert verification_entries[2]["verification_result"]["verification_passed"] is True


if __name__ == "__main__":
    unittest.main()
