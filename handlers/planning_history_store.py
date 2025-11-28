"""Planning history store module.

This module provides JSONL-based storage for planning history.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class PlanningHistoryStore:
    """Manages planning and revision history using JSONL files.
    
    Stores planning history in JSONL format, with one file per task UUID.
    """

    def __init__(self, task_uuid: str, planning_dir: Path) -> None:
        """Initialize the planning history store.
        
        Args:
            task_uuid: Unique identifier for the task
            planning_dir: Planning directory path for this task
        """
        self.task_uuid = task_uuid
        self.logger = logging.getLogger(__name__)
        
        # Use provided planning directory
        self.directory = planning_dir
        
        # Create directory if it doesn't exist
        self.directory.mkdir(parents=True, exist_ok=True)
        
        # Set file path
        self.filepath = self.directory / f"{task_uuid}.jsonl"
        
        # Store metadata for cross-referencing
        self.issue_id = None
        self.task_metadata = {}

    def save_plan(self, plan: dict[str, Any]) -> None:
        """Save initial plan to JSONL file.
        
        Args:
            plan: Plan dictionary to save
        """
        entry = {
            "type": "plan",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "plan": plan,
            "issue_id": self.issue_id,
            "task_uuid": self.task_uuid,
        }
        self._append_to_file(entry)
        self.logger.info(f"Saved plan for task {self.task_uuid}")

    def save_revision(self, revised_plan: dict[str, Any], reflection: dict[str, Any]) -> None:
        """Save plan revision to JSONL file.
        
        Args:
            revised_plan: Revised plan dictionary
            reflection: Reflection that triggered the revision
        """
        entry = {
            "type": "revision",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "reason": reflection.get("reason", "Plan revision needed"),
            "changes": reflection.get("changes", []),
            "updated_plan": revised_plan,
            "issue_id": self.issue_id,
            "task_uuid": self.task_uuid,
        }
        self._append_to_file(entry)
        self.logger.info(f"Saved revision for task {self.task_uuid}")

    def save_reflection(self, reflection: dict[str, Any]) -> None:
        """Save reflection result to JSONL file.

        Args:
            reflection: Reflection dictionary to save

        """
        entry = {
            "type": "reflection",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "evaluation": reflection,
            "issue_id": self.issue_id,
            "task_uuid": self.task_uuid,
        }
        self._append_to_file(entry)
        self.logger.debug("Saved reflection for task %s", self.task_uuid)

    def save_replan_decision(self, replan_entry: dict[str, Any]) -> None:
        """Save replan decision entry to JSONL file.

        再計画判断の履歴を保存します。

        Args:
            replan_entry: 再計画判断エントリ（type, llm_decision等を含む辞書）

        """
        # エントリに必要なメタデータを追加
        entry = dict(replan_entry)
        if "timestamp" not in entry:
            entry["timestamp"] = datetime.now(timezone.utc).isoformat()
        entry["issue_id"] = self.issue_id
        entry["task_uuid"] = self.task_uuid

        self._append_to_file(entry)
        self.logger.debug("Saved replan decision for task %s", self.task_uuid)

    def get_replan_decisions(self) -> list[dict[str, Any]]:
        """Get all replan decision entries.

        Returns:
            List of replan decision entries

        """
        entries = self._read_jsonl()
        return [e for e in entries if e.get("type") == "replan_decision"]

    def get_latest_plan(self) -> dict[str, Any] | None:
        """Get the most recent plan.
        
        Returns:
            Latest plan entry or None if no plan exists
        """
        entries = self._read_jsonl()
        
        # Find the most recent plan or revision entry
        for entry in reversed(entries):
            if entry.get("type") == "plan":
                return entry
            elif entry.get("type") == "revision":
                return entry
        
        return None

    def has_plan(self) -> bool:
        """Check if a plan exists.
        
        Returns:
            True if plan exists, False otherwise
        """
        if not self.filepath.exists():
            return False
        
        entries = self._read_jsonl()
        return any(e.get("type") in ("plan", "revision") for e in entries)

    def get_revision_history(self) -> list[dict[str, Any]]:
        """Get all revision history entries.
        
        Returns:
            List of revision entries
        """
        entries = self._read_jsonl()
        return [e for e in entries if e.get("type") == "revision"]

    def get_all_reflections(self) -> list[dict[str, Any]]:
        """Get all reflection entries.
        
        Returns:
            List of reflection entries
        """
        entries = self._read_jsonl()
        return [e for e in entries if e.get("type") == "reflection"]

    def get_past_executions_for_issue(self, issue_id: str) -> list[dict[str, Any]]:
        """Get past execution history for the same issue/MR.
        
        Searches all task planning directories (running and completed) for entries
        matching the given issue_id.
        
        Args:
            issue_id: Issue or MR identifier
            
        Returns:
            List of all entries for the issue, in chronological order
        """
        all_entries = []
        
        # Search in both running and completed contexts
        # Go up from current planning dir: contexts/running/{uuid}/planning -> contexts/running
        parent = self.directory.parent.parent
        
        # Search both running and completed directories
        for status_dir in [parent / "running", parent / "completed"]:
            if not status_dir.exists():
                continue
                
            for task_dir in status_dir.iterdir():
                if not task_dir.is_dir():
                    continue
                    
                planning_dir = task_dir / "planning"
                if not planning_dir.exists():
                    continue
                
                # Search all JSONL files in this planning directory
                for jsonl_file in planning_dir.glob("*.jsonl"):
                    try:
                        with jsonl_file.open("r", encoding="utf-8") as f:
                            for line in f:
                                if line.strip():
                                    entry = json.loads(line)
                                    if entry.get("issue_id") == issue_id:
                                        all_entries.append(entry)
                    except (json.JSONDecodeError, IOError) as e:
                        self.logger.warning(f"Error reading {jsonl_file}: {e}")
                        continue
        
        # Sort by timestamp
        all_entries.sort(key=lambda x: x.get("timestamp", ""))
        return all_entries

    def _append_to_file(self, entry: dict[str, Any]) -> None:
        """Append an entry to the JSONL file.
        
        Args:
            entry: Entry dictionary to append
        """
        try:
            with self.filepath.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except IOError as e:
            self.logger.error(f"Failed to write to {self.filepath}: {e}")
            raise

    def _read_jsonl(self) -> list[dict[str, Any]]:
        """Read all entries from the JSONL file.
        
        Returns:
            List of entry dictionaries
        """
        if not self.filepath.exists():
            return []
        
        entries = []
        try:
            with self.filepath.open("r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        entries.append(json.loads(line))
        except (json.JSONDecodeError, IOError) as e:
            self.logger.error(f"Failed to read {self.filepath}: {e}")
            return []
        
        return entries
