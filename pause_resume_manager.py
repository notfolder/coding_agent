"""Pause and resume functionality for consumer mode.

This module provides utilities to pause and resume tasks in consumer mode,
including state persistence and restoration.
"""
from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from handlers.task import Task
    from handlers.task_key import TaskKey


class PauseResumeManager:
    """Manager for pause and resume operations."""

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize PauseResumeManager.

        Args:
            config: Application configuration dictionary

        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Get pause/resume configuration
        pause_config = config.get("pause_resume", {})
        self.enabled = pause_config.get("enabled", True)
        self.signal_file = Path(pause_config.get("signal_file", "contexts/pause_signal"))
        self.check_interval = pause_config.get("check_interval", 1)
        self.paused_task_expiry_days = pause_config.get("paused_task_expiry_days", 30)
        
        # Get directory paths
        context_storage_config = config.get("context_storage", {})
        base_dir = Path(context_storage_config.get("base_dir", "contexts"))
        self.base_dir = base_dir
        self.paused_dir = base_dir / "paused"
        self.running_dir = base_dir / "running"
        
        # Create paused directory if it doesn't exist
        self.paused_dir.mkdir(parents=True, exist_ok=True)

    def check_pause_signal(self) -> bool:
        """Check if pause signal file exists.

        Returns:
            True if pause signal is detected, False otherwise

        """
        if not self.enabled:
            return False
        
        if self.signal_file.exists():
            self.logger.info("一時停止シグナルを検出しました: %s", self.signal_file)
            return True
        return False

    def pause_task(
        self,
        task: Task,
        task_uuid: str,
        planning_state: dict[str, Any] | None = None,
    ) -> None:
        """Pause a task and save its state.

        Args:
            task: Task object to pause
            task_uuid: Task UUID
            planning_state: Planning state (if Planning mode is enabled)

        """
        if not self.enabled:
            self.logger.warning("一時停止機能が無効です")
            return

        self.logger.info("タスクを一時停止します: %s", task_uuid)
        
        # Prepare task state dictionary
        task_state = {
            "task_key": task.get_task_key().to_dict(),
            "uuid": task_uuid,
            "user": task.user,
            "paused_at": datetime.now(timezone.utc).isoformat(),
            "status": "paused",
            "resume_count": 0,
            "last_error": None,
            "context_path": f"contexts/paused/{task_uuid}",
        }
        
        # Add planning state if provided
        if planning_state:
            task_state["planning_state"] = planning_state
        
        # Move context directory from running to paused
        running_context_dir = self.running_dir / task_uuid
        paused_context_dir = self.paused_dir / task_uuid
        
        if running_context_dir.exists():
            # Move the directory atomically
            shutil.move(str(running_context_dir), str(paused_context_dir))
            self.logger.info("コンテキストディレクトリを移動しました: %s → %s", running_context_dir, paused_context_dir)
        else:
            self.logger.warning("実行中のコンテキストディレクトリが見つかりません: %s", running_context_dir)
            # Ensure paused directory exists for task_state.json
            paused_context_dir.mkdir(parents=True, exist_ok=True)
        
        # Save task state to paused directory
        task_state_path = paused_context_dir / "task_state.json"
        with task_state_path.open("w") as f:
            json.dump(task_state, f, indent=2, ensure_ascii=False)
        self.logger.info("タスク状態を保存しました: %s", task_state_path)
        
        # Update task label to paused
        try:
            self._update_label_to_paused(task)
        except Exception as e:
            self.logger.exception("ラベル更新中にエラー: %s", e)
        
        # Add comment to task
        try:
            task.comment("タスクを一時停止しました。後で再開されます。")
        except Exception as e:
            self.logger.exception("コメント追加中にエラー: %s", e)
        
        # Note: pause_signal file is intentionally NOT removed here
        # It should be manually removed when ready to resume processing
        self.logger.info("一時停止完了。pause_signalファイルは手動で削除してください: %s", self.signal_file)

    def _update_label_to_paused(self, task: Task) -> None:
        """Update task label from processing to paused.

        Args:
            task: Task object

        """
        # Get label configuration based on task type
        task_type = task.get_task_key().to_dict().get("type", "")
        if task_type.startswith("github"):
            label_config = self.config.get("github", {})
        elif task_type.startswith("gitlab"):
            label_config = self.config.get("gitlab", {})
        else:
            self.logger.warning("不明なタスクタイプ: %s", task_type)
            return
        
        processing_label = label_config.get("processing_label", "coding agent processing")
        paused_label = label_config.get("paused_label", "coding agent paused")
        
        # Remove processing label
        try:
            task.remove_label(processing_label)
            self.logger.info("処理中ラベルを削除しました: %s", processing_label)
        except Exception as e:
            self.logger.warning("処理中ラベルの削除に失敗: %s", e)
        
        # Add paused label
        try:
            task.add_label(paused_label)
            self.logger.info("一時停止ラベルを追加しました: %s", paused_label)
        except Exception as e:
            self.logger.warning("一時停止ラベルの追加に失敗: %s", e)

    def _update_label_to_processing(self, task: Task) -> None:
        """Update task label from paused to processing.

        Args:
            task: Task object

        """
        # Get label configuration based on task type
        task_type = task.get_task_key().to_dict().get("type", "")
        if task_type.startswith("github"):
            label_config = self.config.get("github", {})
        elif task_type.startswith("gitlab"):
            label_config = self.config.get("gitlab", {})
        else:
            self.logger.warning("不明なタスクタイプ: %s", task_type)
            return
        
        processing_label = label_config.get("processing_label", "coding agent processing")
        paused_label = label_config.get("paused_label", "coding agent paused")
        
        # Remove paused label
        try:
            task.remove_label(paused_label)
            self.logger.info("一時停止ラベルを削除しました: %s", paused_label)
        except Exception as e:
            self.logger.warning("一時停止ラベルの削除に失敗: %s", e)
        
        # Add processing label
        try:
            task.add_label(processing_label)
            self.logger.info("処理中ラベルを追加しました: %s", processing_label)
        except Exception as e:
            self.logger.warning("処理中ラベルの追加に失敗: %s", e)

    def get_paused_tasks(self) -> list[dict[str, Any]]:
        """Get list of paused tasks.

        Returns:
            List of paused task dictionaries

        """
        paused_tasks = []
        
        if not self.paused_dir.exists():
            return paused_tasks
        
        # Scan paused directory for task subdirectories
        for task_dir in self.paused_dir.iterdir():
            if not task_dir.is_dir():
                continue
            
            task_state_path = task_dir / "task_state.json"
            if not task_state_path.exists():
                self.logger.warning("task_state.jsonが見つかりません: %s", task_dir)
                continue
            
            try:
                with task_state_path.open() as f:
                    task_state = json.load(f)
                
                # Validate task state
                if task_state.get("status") != "paused":
                    self.logger.warning("無効な状態: %s", task_state.get("status"))
                    continue
                
                paused_tasks.append(task_state)
                self.logger.info("一時停止タスクを検出: %s", task_state.get("uuid"))
            except Exception as e:
                self.logger.exception("task_state.jsonの読み込みエラー: %s", e)
                continue
        
        return paused_tasks

    def prepare_resume_task_dict(self, task_state: dict[str, Any]) -> dict[str, Any]:
        """Prepare task dictionary for resuming.

        Args:
            task_state: Task state dictionary from task_state.json

        Returns:
            Task dictionary for queue

        """
        task_dict = task_state["task_key"].copy()
        task_dict["uuid"] = task_state["uuid"]
        task_dict["user"] = task_state.get("user")
        task_dict["is_resumed"] = True
        task_dict["paused_context_path"] = task_state.get("context_path")
        
        return task_dict

    def restore_task_context(
        self,
        task: Task,
        task_uuid: str,
    ) -> dict[str, Any] | None:
        """Restore task context from paused state.

        Args:
            task: Task object
            task_uuid: Task UUID

        Returns:
            Planning state dictionary if available, None otherwise

        """
        paused_context_dir = self.paused_dir / task_uuid
        running_context_dir = self.running_dir / task_uuid
        
        if not paused_context_dir.exists():
            self.logger.error("一時停止コンテキストディレクトリが見つかりません: %s", paused_context_dir)
            return None
        
        # Load task state
        task_state_path = paused_context_dir / "task_state.json"
        planning_state = None
        if task_state_path.exists():
            try:
                with task_state_path.open() as f:
                    task_state = json.load(f)
                    planning_state = task_state.get("planning_state")
                    
                # Increment resume count
                task_state["resume_count"] = task_state.get("resume_count", 0) + 1
                task_state["resumed_at"] = datetime.now(timezone.utc).isoformat()
                
                # Update task state file
                with task_state_path.open("w") as f:
                    json.dump(task_state, f, indent=2, ensure_ascii=False)
            except Exception as e:
                self.logger.exception("task_state.jsonの読み込みエラー: %s", e)
        
        # Move context directory from paused to running
        try:
            shutil.move(str(paused_context_dir), str(running_context_dir))
            self.logger.info("コンテキストディレクトリを移動しました: %s → %s", paused_context_dir, running_context_dir)
        except Exception as e:
            self.logger.exception("コンテキストディレクトリの移動エラー: %s", e)
            return None
        
        # Update label to processing
        try:
            self._update_label_to_processing(task)
        except Exception as e:
            self.logger.exception("ラベル更新中にエラー: %s", e)
        
        # Add resume comment
        try:
            if planning_state and planning_state.get("enabled"):
                task.comment("一時停止されたタスクを再開します（Planning実行中）。")
            else:
                task.comment("一時停止されたタスクを再開します。")
        except Exception as e:
            self.logger.exception("コメント追加中にエラー: %s", e)
        
        return planning_state
