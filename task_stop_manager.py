"""Task stop functionality based on assignee status.

This module provides utilities to stop tasks when the coding agent
is unassigned from an issue or merge request.
"""
from __future__ import annotations

import logging
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from handlers.task import Task


class TaskStopManager:
    """Manager for task stop operations based on assignee status.
    
    Monitors whether the coding agent bot is still assigned to an issue/MR,
    and stops the task if the bot is unassigned.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize TaskStopManager.

        Args:
            config: Application configuration dictionary

        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Get task_stop configuration (with defaults)
        task_stop_config = config.get("task_stop", {})
        self.enabled = task_stop_config.get("enabled", True)
        self.check_interval = task_stop_config.get("check_interval", 1)
        self.min_check_interval_seconds = task_stop_config.get("min_check_interval_seconds", 30)
        
        # Get directory paths
        context_storage_config = config.get("context_storage", {})
        base_dir = Path(context_storage_config.get("base_dir", "contexts"))
        self.base_dir = base_dir
        self.completed_dir = base_dir / "completed"
        self.running_dir = base_dir / "running"
        
        # Create completed directory if it doesn't exist
        self.completed_dir.mkdir(parents=True, exist_ok=True)
        
        # Track last check time
        self._last_check_time: float | None = None
        self._check_counter = 0

    def _get_bot_name(self, task: Task) -> str | None:
        """Get the bot name for the task type.

        Args:
            task: Task object

        Returns:
            Bot name or None if not configured

        """
        task_key = task.get_task_key()
        task_type = task_key.to_dict().get("type", "")
        
        if task_type.startswith("github"):
            # Get from config
            return self.config.get("github", {}).get("bot_name")
        elif task_type.startswith("gitlab"):
            # Get from config
            return self.config.get("gitlab", {}).get("bot_name")
        
        return None

    def should_check_now(self) -> bool:
        """Determine if assignee check should be performed now.

        Returns:
            True if check should be performed, False otherwise

        """
        if not self.enabled:
            return False
        
        # Check interval counter
        self._check_counter += 1
        if self.check_interval > 0 and self._check_counter % self.check_interval != 0:
            return False
        
        # Check time interval
        current_time = time.time()
        if self._last_check_time is None:
            self._last_check_time = current_time
            return True
        
        elapsed = current_time - self._last_check_time
        if elapsed >= self.min_check_interval_seconds:
            self._last_check_time = current_time
            return True
        
        return False

    def check_assignee_status(self, task: Task) -> bool:
        """Check if the bot is still assigned to the task.

        Args:
            task: Task object

        Returns:
            True if bot is assigned, False if unassigned

        """
        if not self.enabled:
            return True
        
        bot_name = self._get_bot_name(task)
        if not bot_name:
            self.logger.debug("ボット名が設定されていないため、アサインチェックをスキップ")
            return True
        
        try:
            # Refresh assignee list from API
            assignees = task.refresh_assignees()
            self.logger.debug("アサイン状況: %s", assignees)
            
            is_assigned = bot_name in assignees
            if not is_assigned:
                self.logger.info("ボット(%s)がアサインから外されました。タスクを停止します。", bot_name)
            
            return is_assigned
            
        except Exception as e:
            # On error, continue processing (don't stop)
            self.logger.warning("アサイン状況の確認中にエラー: %s。処理を継続します。", e)
            return True

    def stop_task(
        self,
        task: Task,
        task_uuid: str,
        *,
        planning_state: dict[str, Any] | None = None,
        llm_call_count: int | None = None,
    ) -> None:
        """非推奨: stop_taskは直接使用せず、TaskContextManager.stop()を使用してください.

        Args:
            task: Task object to stop
            task_uuid: Task UUID
            planning_state: Planning state (if Planning mode is enabled)
            llm_call_count: Number of LLM calls made (for Context Storage mode)

        """
        self.logger.warning(
            "stop_task()は非推奨です。TaskContextManager.stop()とpost_stop_notification()を使用してください"
        )
        self.logger.info("タスクを停止します: %s", task_uuid)
        
        # Post stop notification
        self.post_stop_notification(task, planning_state=planning_state, llm_call_count=llm_call_count)
        
        # Move context to completed directory (legacy behavior)
        try:
            self._move_to_completed(task_uuid)
        except Exception as e:
            self.logger.exception("コンテキスト移動中にエラー: %s", e)
        
        self.logger.info("タスク停止完了: %s", task_uuid)

    def post_stop_notification(
        self,
        task: Task,
        *,
        planning_state: dict[str, Any] | None = None,
        llm_call_count: int | None = None,
    ) -> None:
        """タスク停止の通知を投稿し、ラベルを更新する.

        Args:
            task: Task object
            planning_state: Planning state (if Planning mode is enabled)
            llm_call_count: Number of LLM calls made (for Context Storage mode)

        """
        # Build stop comment
        stop_comment = self._build_stop_comment(planning_state, llm_call_count)
        
        # Post stop comment
        try:
            task.comment(stop_comment)
        except Exception as e:
            self.logger.exception("停止コメント投稿中にエラー: %s", e)
        
        # Update labels
        try:
            self._update_label_to_stopped(task)
        except Exception as e:
            self.logger.exception("ラベル更新中にエラー: %s", e)

    def _build_stop_comment(
        self,
        planning_state: dict[str, Any] | None = None,
        llm_call_count: int | None = None,
    ) -> str:
        """Build the stop comment message.

        Args:
            planning_state: Planning state (if Planning mode is enabled)
            llm_call_count: Number of LLM calls made (for Context Storage mode)

        Returns:
            Stop comment string

        """
        timestamp = datetime.now(timezone.utc).isoformat()
        
        lines = [
            "## ⛔ タスク停止",
            "",
            "コーディングエージェントのアサインが解除されたため、タスクを停止しました。",
            "",
            f"**停止時刻:** {timestamp}",
        ]
        
        if planning_state and planning_state.get("enabled"):
            # Planning mode
            action_counter = planning_state.get("action_counter", 0)
            total_actions = planning_state.get("total_actions", "?")
            phase = planning_state.get("current_phase", "unknown")
            lines.append(f"**処理状況:** {action_counter}/{total_actions} 完了")
            lines.append(f"**フェーズ:** {phase}")
        elif llm_call_count is not None:
            # Context Storage mode
            lines.append(f"**LLM対話回数:** {llm_call_count}")
        
        lines.extend([
            "",
            "タスクを再開する場合は、コーディングエージェントを再度アサインし、",
            "`coding agent` ラベルを付与してください。",
        ])
        
        return "\n".join(lines)

    def _update_label_to_stopped(self, task: Task) -> None:
        """Update task label from processing to stopped.

        Args:
            task: Task object

        """
        task_key = task.get_task_key()
        task_type = task_key.to_dict().get("type", "")
        
        if task_type.startswith("github"):
            label_config = self.config.get("github", {})
        elif task_type.startswith("gitlab"):
            label_config = self.config.get("gitlab", {})
        else:
            self.logger.warning("不明なタスクタイプ: %s", task_type)
            return
        
        processing_label = label_config.get("processing_label", "coding agent processing")
        stopped_label = label_config.get("stopped_label", "coding agent stopped")
        
        # Remove processing label
        try:
            task.remove_label(processing_label)
            self.logger.info("処理中ラベルを削除しました: %s", processing_label)
        except Exception as e:
            self.logger.warning("処理中ラベルの削除に失敗: %s", e)
        
        # Add stopped label
        try:
            task.add_label(stopped_label)
            self.logger.info("停止ラベルを追加しました: %s", stopped_label)
        except Exception as e:
            self.logger.warning("停止ラベルの追加に失敗: %s", e)

    def _move_to_completed(self, task_uuid: str) -> None:
        """Move context storage to completed directory.

        Args:
            task_uuid: Task UUID

        """
        running_context_dir = self.running_dir / task_uuid
        completed_context_dir = self.completed_dir / task_uuid
        
        if running_context_dir.exists():
            shutil.move(str(running_context_dir), str(completed_context_dir))
            self.logger.info(
                "コンテキストディレクトリを移動しました: %s → %s",
                running_context_dir,
                completed_context_dir,
            )
        else:
            self.logger.warning(
                "実行中のコンテキストディレクトリが見つかりません: %s",
                running_context_dir,
            )
