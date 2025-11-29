"""Planning coordinator module.

This module provides the main coordination logic for planning-based task execution.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from handlers.replan_decision import ReplanDecision, ReplanType, TargetPhase
from handlers.replan_manager import ReplanManager

# 共通の日付フォーマット定数
DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"

# JSON出力の切り詰め制限定数
JSON_TRUNCATION_LIMIT = 1000

# ツール引数表示の最大文字数
TOOL_ARGS_MAX_LENGTH = 40

if TYPE_CHECKING:
    from clients.llm_base import LLMClient
    from clients.mcp_tool_client import MCPToolClient
    from context_storage.task_context_manager import TaskContextManager
    from handlers.task import Task


class PlanningCoordinator:
    """Coordinates planning-based task execution.

    Manages the planning process including goal understanding, task decomposition,
    action execution, reflection, and plan revision.
    """

    def __init__(
        self,
        config: dict[str, Any],
        llm_client: LLMClient | None,
        mcp_clients: dict[str, MCPToolClient],
        task: Task,
        context_manager: TaskContextManager,
    ) -> None:
        """Initialize the planning coordinator.

        Args:
            config: Planning configuration
            llm_client: LLM client instance to use. If None, a new client will be created.
            mcp_clients: Dictionary of MCP tool clients
            task: Task object to process
            context_manager: TaskContextManager instance for unified context management

        """
        self.config = config
        self.mcp_clients = mcp_clients
        self.task = task
        self.context_manager = context_manager
        self.logger = logging.getLogger(__name__)

        # Get stores from context manager
        self.history_store = context_manager.get_planning_store()
        message_store = context_manager.get_message_store()

        # Set issue_id for cross-task history tracking from TaskKey
        task_key = task.get_task_key()
        task_dict = task_key.to_dict()
        # GitHub: number, GitLab: issue_iid or mr_iid
        issue_id = task_dict.get("number") or task_dict.get("issue_iid") or task_dict.get("mr_iid")
        if issue_id:
            self.history_store.issue_id = str(issue_id)

        # Track checklist comment ID for updates
        self.checklist_comment_id: int | str | None = None

        # Use provided LLM client or create new one if not provided
        if llm_client is not None:
            self.llm_client = llm_client
            # Update message_store and context_dir to use planning's context
            self.llm_client.message_store = message_store
            self.llm_client.context_dir = context_manager.context_dir
        else:
            # Create planning-specific LLM client
            from clients.lm_client import get_llm_client

            # Get the main config for LLM client initialization
            main_config = config.get("main_config", {})

            # Get functions and tools from MCP clients
            functions = []
            tools = []
            if main_config.get("llm", {}).get("function_calling", True):
                for mcp_client in mcp_clients.values():
                    functions.extend(mcp_client.get_function_calling_functions())
                    tools.extend(mcp_client.get_function_calling_tools())

            self.llm_client = get_llm_client(
                main_config,
                functions=functions if functions else None,
                tools=tools if tools else None,
                message_store=message_store,
                context_dir=context_manager.context_dir,
            )

        # Load and send planning-specific system prompt
        self._load_planning_system_prompt()

        # Current state
        self.current_phase = "planning"
        self.current_plan = None
        self.action_counter = 0
        self.revision_counter = 0

        # 再計画管理用のReplanManagerを初期化
        available_tools = self._get_available_tool_names()
        self.replan_manager = ReplanManager(
            config=config,
            history_store=self.history_store,
            available_tools=available_tools,
        )

        # エラーカウンター(再計画判断用)
        self.error_count = 0
        self.consecutive_errors = 0

        # 計画リビジョン番号(チェックリスト表示用)
        self.plan_revision_number = 0

        # LLM呼び出し回数カウンター（LLM呼び出しコメント機能用）
        self.llm_call_count = 0

        # LLM呼び出しコメント機能の有効/無効
        llm_call_comments_config = config.get("llm_call_comments", {})
        self.llm_call_comments_enabled = llm_call_comments_config.get("enabled", True)
        self.logger.info("LLM呼び出しコメント機能: %s", "有効" if self.llm_call_comments_enabled else "無効")

        # フェーズ別のデフォルトメッセージ
        self.phase_default_messages: dict[str, str] = {
            "pre_planning": "タスク内容の分析と情報収集が完了しました",
            "planning": "実行計画の作成が完了しました",
            "execution": "アクションの実行が完了しました",
            "reflection": "実行結果の分析が完了しました",
            "revision": "計画の修正が完了しました",
            "verification": "実装の検証が完了しました",
            "replan_decision": "再計画の判断が完了しました",
        }

        # Pause/resume support
        self.pause_manager = None  # Will be set by TaskHandler

        # Task stop support
        self.stop_manager = None  # Will be set by TaskHandler

        # Comment detection support
        self.comment_detection_manager = None  # Will be set by TaskHandler

        # Execution environment manager
        self.execution_manager = None  # Will be set by TaskHandler

        # Checkbox tracking for progress updates
        self.plan_comment_id = None  # ID of the comment containing the checklist

        # 計画前情報収集フェーズの結果
        self.pre_planning_result: dict[str, Any] | None = None

        # 計画で選択された実行環境名
        self.selected_environment: str | None = None

        # PrePlanningManagerの初期化（有効な場合）
        self.pre_planning_manager: Any = None
        pre_planning_config = config.get("pre_planning", {})
        if pre_planning_config.get("enabled", True):
            self._init_pre_planning_manager(pre_planning_config)

    def _init_pre_planning_manager(self, pre_planning_config: dict[str, Any]) -> None:
        """PrePlanningManagerを初期化する.

        Args:
            pre_planning_config: 計画前情報収集の設定

        """
        from handlers.pre_planning_manager import PrePlanningManager

        self.pre_planning_manager = PrePlanningManager(
            config=pre_planning_config,
            llm_client=self.llm_client,
            mcp_clients=self.mcp_clients,
            task=self.task,
        )
        # コンテキストマネージャを設定
        self.pre_planning_manager.context_manager = self.context_manager
        self.logger.info("PrePlanningManagerを初期化しました")

    def _get_available_tool_names(self) -> list[str]:
        """MCPクライアントから利用可能なツール名のリストを取得する.

        Returns:
            ツール名のリスト

        """
        tool_names = []
        for client_name, mcp_client in self.mcp_clients.items():
            try:
                tools = mcp_client.get_function_calling_tools()
                for tool in tools:
                    if isinstance(tool, dict) and "function" in tool:
                        tool_names.append(tool["function"].get("name", ""))
                    elif hasattr(tool, "name"):
                        tool_names.append(tool.name)
            except Exception:
                self.logger.warning("ツール一覧の取得に失敗: %s", client_name)
        return [name for name in tool_names if name]

    def execute_with_planning(self) -> bool:
        """Execute task with planning capabilities.
        
        Main execution loop that handles planning, execution, reflection, and revision.
        
        Returns:
            True if task completed successfully, False otherwise
        """
        try:
            # Check for pause signal before starting
            if self._check_pause_signal():
                self.logger.info("一時停止シグナルを検出、タスクを一時停止します")
                self._handle_pause()
                return True  # Return success to avoid marking as failed

            # Check for stop signal before starting
            if self._check_stop_signal():
                self.logger.info("アサイン解除を検出、タスクを停止します")
                self._handle_stop()
                return True  # Return success to avoid marking as failed

            # Check for new comments before starting
            self._check_and_add_new_comments()

            # Step 0.5: Check for inheritance context and post notification
            self._handle_context_inheritance()

            # Step 0: Execute pre-planning phase (計画前情報収集フェーズ)
            if self.pre_planning_manager is not None:
                self._post_phase_comment("pre_planning", "started", "タスク内容を分析し、必要な情報を収集しています...")
                self.pre_planning_result = self._execute_pre_planning_phase()
                self._post_phase_comment("pre_planning", "completed", "計画前情報収集が完了しました")

            # Post planning start comment
            self._post_phase_comment("planning", "started", "Beginning task analysis and planning...")

            # Step 1: Check for existing plan
            if self.history_store.has_plan():
                self.logger.info("Found existing plan, loading...")
                plan_entry = self.history_store.get_latest_plan()
                if plan_entry:
                    self.current_plan = plan_entry.get("plan") or plan_entry.get("updated_plan")
                    self.current_phase = "execution"
                    self._post_phase_comment("planning", "completed", "Loaded existing plan from history.")
            else:
                # Step 2: Execute planning phase
                self.logger.info("No existing plan, executing planning phase...")
                self.current_plan = self._execute_planning_phase()
                if self.current_plan:
                    self.history_store.save_plan(self.current_plan)
                    # Post plan to Issue/MR as markdown checklist
                    self._post_plan_as_checklist(self.current_plan)
                    self.current_phase = "execution"
                    self._post_phase_comment("planning", "completed", "Created execution plan with action items.")
                else:
                    self.logger.error("Planning phase failed")
                    self._post_phase_comment("planning", "failed", "Could not generate a valid execution plan.")
                    return False

            # Check for pause signal after planning
            if self._check_pause_signal():
                self.logger.info("一時停止シグナルを検出、タスクを一時停止します")
                self._handle_pause()
                return True

            # Check for stop signal after planning
            if self._check_stop_signal():
                self.logger.info("アサイン解除を検出、タスクを停止します")
                self._handle_stop()
                return True

            # Check for new comments after planning phase
            self._check_and_add_new_comments()

            # Post execution start
            self._post_phase_comment("execution", "started", "Beginning execution of planned actions...")

            # Step 3: Execution loop
            max_iterations = self.config.get("max_subtasks", 100)
            iteration = 0

            while iteration < max_iterations and not self._is_complete():
                iteration += 1

                # Check for pause signal before each action
                if self._check_pause_signal():
                    self.logger.info("一時停止シグナルを検出、タスクを一時停止します")
                    self._handle_pause()
                    return True

                # Check for stop signal before each action
                if self._check_stop_signal():
                    self.logger.info("アサイン解除を検出、タスクを停止します")
                    self._handle_stop()
                    return True

                # Check for new comments before each action
                self._check_and_add_new_comments()

                # Execute next action
                result = self._execute_action()

                if result is None:
                    self.logger.warning("No more actions to execute")
                    break

                # エラー追跡の更新
                current_action = result.get("action", {})
                if result.get("status") == "error":
                    self.error_count += 1
                    self.consecutive_errors += 1

                    error_msg = result.get("error", "Unknown error occurred")
                    self._post_phase_comment(
                        "execution", "failed", f"Action failed: {error_msg}",
                    )

                    # 再計画判断をLLMに依頼
                    if self.replan_manager.enabled:
                        decision = self._request_execution_replan_decision(
                            current_action, result,
                        )
                        if self._handle_replan(decision):
                            # 再計画が実行された場合、ループを継続
                            continue

                    # Continue or stop based on configuration
                    if not self.config.get("continue_on_error", False):
                        return False
                else:
                    # 成功した場合はエラーカウンターをリセット
                    self.consecutive_errors = 0

                # Update progress checklist
                self._update_checklist_progress(self.action_counter - 1)

                # Check if reflection is needed
                if self._should_reflect(result):
                    # Check for pause signal before reflection
                    if self._check_pause_signal():
                        self.logger.info("一時停止シグナルを検出、タスクを一時停止します")
                        self._handle_pause()
                        return True

                    # Check for stop signal before reflection
                    if self._check_stop_signal():
                        self.logger.info("アサイン解除を検出、タスクを停止します")
                        self._handle_stop()
                        return True

                    # Check for new comments before reflection
                    self._check_and_add_new_comments()

                    self._post_phase_comment("reflection", "started", f"Analyzing results after {self.action_counter} actions...")
                    self.current_phase = "reflection"
                    reflection = self._execute_reflection_phase(result)

                    if reflection and reflection.get("plan_revision_needed"):
                        # Check for pause signal before revision
                        if self._check_pause_signal():
                            self.logger.info("一時停止シグナルを検出、タスクを一時停止します")
                            self._handle_pause()
                            return True

                        # Check for stop signal before revision
                        if self._check_stop_signal():
                            self.logger.info("アサイン解除を検出、タスクを停止します")
                            self._handle_stop()
                            return True

                        # Check for new comments before revision
                        self._check_and_add_new_comments()

                        # Revise plan if needed
                        self._post_phase_comment("revision", "started", "Plan revision needed based on reflection.")
                        self.current_phase = "revision"
                        revised_plan = self._revise_plan(reflection)
                        if revised_plan:
                            self.current_plan = revised_plan
                            self._post_phase_comment("revision", "completed", "Plan has been revised and updated.")
                        else:
                            self._post_phase_comment("revision", "failed", "Could not revise plan.")
                    else:
                        self._post_phase_comment("reflection", "completed", "Reflection complete, continuing with current plan.")

                    # Reset to execution phase
                    self.current_phase = "execution"

                # Check for completion
                if result.get("done"):
                    self.logger.info("Task completed successfully")
                    break

            # Step 4: Verification phase
            verification_config = self.config.get("verification", {})
            if verification_config.get("enabled", True):
                self.logger.info("All planned actions executed, starting verification phase")
                self._post_phase_comment("verification", "started", "Verifying task completion...")

                max_verification_rounds = verification_config.get("max_rounds", 2)
                verification_round = 0

                while verification_round < max_verification_rounds:
                    verification_round += 1

                    # Check for pause/stop signals before verification
                    if self._check_pause_signal():
                        self.logger.info("Pause signal detected during verification")
                        self._handle_pause()
                        return True

                    if self._check_stop_signal():
                        self.logger.info("Stop signal detected during verification")
                        self._handle_stop()
                        return True

                    # Check for new comments
                    self._check_and_add_new_comments()

                    verification_result = self._execute_verification_phase()

                    if not verification_result:
                        self._post_phase_comment("verification", "failed", "Could not parse verification result")
                        break

                    self._post_verification_result(verification_result)

                    if verification_result.get("verification_passed"):
                        self.logger.info("Verification passed!")
                        self._post_phase_comment("verification", "completed", "All requirements verified ✅")
                        break

                    additional_actions = verification_result.get("additional_actions", [])

                    if not additional_actions:
                        issues_list = "\n".join(
                            f"- {issue}" for issue in verification_result.get("issues_found", [])
                        )
                        self._post_phase_comment(
                            "verification",
                            "failed",
                            f"Verification failed but no additional actions provided. Issues found:\n{issues_list}",
                        )
                        break

                    # 追加アクションを計画に追加
                    self.logger.info("Adding %d additional actions to plan", len(additional_actions))
                    current_actions = self.current_plan.get("action_plan", {}).get("actions", [])
                    current_actions.extend(additional_actions)

                    # チェックリスト更新
                    self._update_checklist_for_additional_work(verification_result, additional_actions)

                    # 追加アクションを実行
                    self._post_phase_comment(
                        "execution",
                        "started",
                        f"Executing {len(additional_actions)} additional actions to address verification issues...",
                    )

                    # 追加アクション実行ループ用の別カウンター
                    additional_work_iteration = 0
                    max_additional_iterations = min(len(additional_actions) * 3, max_iterations)

                    while not self._is_complete():
                        if additional_work_iteration >= max_additional_iterations:
                            self.logger.warning("Max iterations reached during additional work")
                            break

                        additional_work_iteration += 1

                        # Check for pause/stop signals
                        if self._check_pause_signal():
                            self.logger.info("Pause signal detected during additional work")
                            self._handle_pause()
                            return True

                        if self._check_stop_signal():
                            self.logger.info("Stop signal detected during additional work")
                            self._handle_stop()
                            return True

                        self._check_and_add_new_comments()

                        result = self._execute_action()

                        if result is None:
                            break

                        # エラーハンドリング
                        if result.get("status") == "error":
                            self.error_count += 1
                            self.consecutive_errors += 1
                            error_msg = result.get("error", "Unknown error occurred")
                            self._post_phase_comment("execution", "failed", f"Action failed: {error_msg}")

                            if self.replan_manager.enabled:
                                decision = self._request_execution_replan_decision(
                                    result.get("action", {}), result,
                                )
                                if self._handle_replan(decision):
                                    continue

                            if not self.config.get("continue_on_error", False):
                                return False
                        else:
                            self.consecutive_errors = 0

                        self._update_checklist_progress(self.action_counter - 1)

                        if result.get("done"):
                            break

                    # 次の検証ラウンドへ
                    self.logger.info(
                        "Completed additional work, re-verifying (round %d/%d)",
                        verification_round + 1,
                        max_verification_rounds,
                    )

            # Mark all tasks complete
            self._mark_checklist_complete()
            self._post_phase_comment("execution", "completed", "All planned actions have been executed successfully.")

            return True

        except Exception as e:
            self.logger.exception("Planning execution failed: %s", e)
            self._post_phase_comment("execution", "failed", f"Error during execution: {str(e)}")
            return False

    def _handle_pause(self) -> None:
        """Handle pause operation for planning mode."""
        if self.pause_manager is None:
            self.logger.warning("Pause manager not set, cannot pause")
            return

        # Get current planning state
        planning_state = self.get_planning_state()

        # Pause the task with planning state
        self.pause_manager.pause_task(self.task, self.task.uuid, planning_state=planning_state)

    def _handle_context_inheritance(self) -> None:
        """過去コンテキスト引き継ぎを処理する.

        TaskContextManagerから引き継ぎコンテキストを取得し、
        通知コメントを投稿し、初期コンテキストをLLMに設定します。
        """
        # context_managerから引き継ぎコンテキストを確認
        if not self.context_manager.has_inheritance_context():
            return

        try:
            # 引き継ぎ通知コメントを投稿
            notification = self.context_manager.get_inheritance_notification_comment()
            if notification and hasattr(self.task, "comment"):
                self.task.comment(notification)
                self.logger.info("過去コンテキスト引き継ぎ通知を投稿しました")

            # 引き継ぎコンテキストを取得
            inheritance_context = self.context_manager.get_inheritance_context()
            if inheritance_context is None:
                return

            # 初期コンテキストメッセージを作成してLLMに追加
            # （user_requestは既にget_prompt()で取得済みのため、ここでは最終要約のみを追加）
            summary_with_prefix = self._format_inherited_summary(inheritance_context)
            if summary_with_prefix:
                # LLMにアシスタントロールで引き継ぎ情報を追加
                # Note: send_user_message/send_system_promptではなく、
                # コンテキストの最初に履歴として追加する形式を使用
                # add_assistant_messageはLLMClient基底クラスで定義済み
                self.llm_client.add_assistant_message(summary_with_prefix)
                self.logger.info("引き継ぎコンテキストをLLMに追加しました")

        except Exception as e:
            self.logger.warning("過去コンテキスト引き継ぎの処理に失敗: %s", e)

    def _format_inherited_summary(self, inheritance_context: Any) -> str | None:
        """引き継ぎコンテキストから要約テキストをフォーマットする.

        Args:
            inheritance_context: InheritanceContextインスタンス

        Returns:
            フォーマットされた要約テキスト、または None

        """
        if inheritance_context is None:
            return None

        try:
            prev = inheritance_context.previous_context
            final_summary = inheritance_context.final_summary
            planning_summary = inheritance_context.planning_summary

            if not final_summary:
                return None

            completed_at_str = (
                prev.completed_at.strftime("%Y-%m-%d %H:%M:%S")
                if prev.completed_at
                else "不明"
            )

            lines = [
                "前回の処理要約:",
                f"(引き継ぎ元: {prev.uuid[:8]}, 処理日時: {completed_at_str})",
                "",
                final_summary,
            ]

            # Planning Modeサマリーがある場合は追加
            if planning_summary:
                lines.extend([
                    "",
                    "=== Previous Plan Summary ===",
                ])

                plan_summary = planning_summary.get("previous_plan_summary", {})
                if plan_summary:
                    goal = plan_summary.get("goal", "")
                    if goal:
                        lines.append(f"Goal: {goal}")
                    subtasks = plan_summary.get("subtasks", [])
                    if subtasks:
                        lines.append(f"Subtasks: {', '.join(subtasks[:5])}")

                recommendations = planning_summary.get("recommendations", [])
                if recommendations:
                    lines.append("")
                    lines.append("=== Recommendations ===")
                    for rec in recommendations:
                        lines.append(f"- {rec}")

            return "\n".join(lines)

        except Exception as e:
            self.logger.warning("引き継ぎ要約のフォーマットに失敗: %s", e)
            return None


    def _execute_pre_planning_phase(self) -> dict[str, Any] | None:
        """計画前情報収集フェーズを実行する.

        Returns:
            計画フェーズへの引き継ぎデータ、または None

        """
        if self.pre_planning_manager is None:
            return None

        try:
            self.logger.info("計画前情報収集フェーズを開始します")
            result = self.pre_planning_manager.execute()
            self.logger.info("計画前情報収集フェーズが完了しました")
            return result
        except Exception as e:
            self.logger.warning("計画前情報収集フェーズでエラーが発生しました: %s", e)
            return None

    def _execute_planning_phase(self) -> dict[str, Any] | None:
        """Execute the planning phase.
        
        計画作成と同時に実行環境を選択します。
        
        Returns:
            Planning result dictionary or None if planning failed
        """
        try:
            # Get past executions for context from TaskKey
            task_key = self.task.get_task_key()
            task_dict = task_key.to_dict()
            # GitHub: number, GitLab: issue_iid or mr_iid
            issue_id = task_dict.get("number") or task_dict.get("issue_iid") or task_dict.get("mr_iid")
            past_history = []
            if issue_id:
                past_history = self.history_store.get_past_executions_for_issue(str(issue_id))

            # Prepare planning prompt
            planning_prompt = self._build_planning_prompt(past_history)

            # Request plan from LLM
            self.llm_client.send_user_message(planning_prompt)
            response, _, tokens = self.llm_client.get_response()  # Unpack tuple with tokens
            self.logger.info("Planning LLM response (tokens: %d)", tokens)

            # トークン数を記録
            self.context_manager.update_statistics(llm_calls=1, tokens=tokens)

            # Parse response
            plan = self._parse_planning_response(response)

            # 計画応答から選択された環境を抽出
            if plan:
                self.selected_environment = self._extract_selected_environment(plan)
                self.logger.info("選択された実行環境: %s", self.selected_environment)

            # LLM呼び出し完了コメントを投稿
            self._post_llm_call_comment("planning", plan)

            return plan

        except Exception as e:
            self.logger.exception("Planning phase execution failed")
            # LLMエラーコメントを投稿
            self._post_llm_error_comment("planning", str(e))
            return None

    def _extract_selected_environment(self, plan: dict[str, Any]) -> str | None:
        """計画応答から選択された実行環境を抽出する.

        仕様書に従い、計画応答のselected_environmentフィールドから
        環境名を抽出します。

        Args:
            plan: 計画応答の辞書

        Returns:
            選択された環境名、または見つからない場合はNone

        """
        if not isinstance(plan, dict):
            return None

        selected_env = plan.get("selected_environment")

        if selected_env is None:
            self.logger.info("計画応答にselected_environmentが含まれていません")
            return None

        # selected_environmentが辞書形式の場合
        if isinstance(selected_env, dict):
            env_name = selected_env.get("name")
            reasoning = selected_env.get("reasoning", "理由なし")
            if env_name:
                self.logger.info(
                    "環境 '%s' が選択されました。理由: %s",
                    env_name,
                    reasoning[:100] if len(reasoning) > 100 else reasoning,
                )
                return env_name
            return None

        # selected_environmentが文字列形式の場合
        if isinstance(selected_env, str):
            return selected_env

        return None

    def _execute_action(self) -> dict[str, Any] | None:
        """Execute the next action from the plan.
        
        Returns:
            Action result dictionary or None if no action to execute
        """
        try:
            if not self.current_plan:
                return None

            # Get next action from plan
            action_plan = self.current_plan.get("action_plan", {})
            actions = action_plan.get("actions", [])

            if self.action_counter >= len(actions):
                # No more actions
                return {"done": True, "status": "completed"}

            current_action = actions[self.action_counter]
            task_id = current_action.get("task_id", f"task_{self.action_counter + 1}")
            self.action_counter += 1

            # Execute the action via LLM
            action_prompt = self._build_action_prompt(current_action)
            self.llm_client.send_user_message(action_prompt)

            # Get LLM response with function calls
            resp, functions, tokens = self.llm_client.get_response()
            self.logger.info("Action execution LLM response: %s", resp)

            # トークン数を記録
            self.context_manager.update_statistics(llm_calls=1, tokens=tokens)

            # Initialize error state for tool execution
            error_state = {"last_tool": None, "tool_error_count": 0}

            # Process function calls if any
            if functions:
                if not isinstance(functions, list):
                    functions = [functions]

                # Execute all function calls
                for function in functions:
                    if self._execute_function_call(function, error_state, task_id):
                        # Critical error occurred
                        return {
                            "status": "error",
                            "error": "Too many consecutive tool errors",
                            "action": current_action,
                        }

            # Try to parse JSON response
            try:
                data = json.loads(resp) if isinstance(resp, str) else resp

                # LLM呼び出し完了コメントを投稿
                # Note: commentフィールドの投稿はここで統一的に処理される
                self._post_llm_call_comment("execution", data, task_id)

                # Check if done
                if isinstance(data, dict) and data.get("done"):
                    return {"done": True, "status": "completed", "result": data}

                return {"status": "success", "result": data, "action": current_action}
            except (json.JSONDecodeError, ValueError):
                # テキスト応答の場合もLLM呼び出しコメントを投稿
                self._post_llm_call_comment("execution", None, task_id)
                return {"status": "success", "result": resp, "action": current_action}

        except Exception as e:
            self.logger.exception("Action execution failed: %s", e)
            # LLMエラーコメントを投稿
            self._post_llm_error_comment("execution", str(e))
            return {"status": "error", "error": str(e)}

    def _execute_function_call(
        self,
        function: dict[str, Any],
        error_state: dict[str, Any],
        task_id: str | None = None,
    ) -> bool:
        """Execute a single function call.
        
        Args:
            function: Function call information (dict or object with name/arguments)
            error_state: Error state tracking dictionary
            task_id: 現在実行中のアクションID（エラーコメント用）
            
        Returns:
            True if critical error occurred (should abort), False otherwise
        """
        # Maximum consecutive tool errors before aborting
        MAX_CONSECUTIVE_TOOL_ERRORS = 3

        try:
            # Get function name
            name = function["name"] if isinstance(function, dict) else function.name

            # Parse MCP server and tool name
            if "_" not in name:
                self.logger.error("Invalid function name format: %s", name)
                return False

            mcp_server, tool_name = name.split("_", 1)

            # Get arguments
            args = function["arguments"] if isinstance(function, dict) else function.arguments
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    self.logger.error("Failed to parse arguments JSON: %s", args)
                    return False

            self.logger.info("Executing function: %s with args: %s", name, args)

            # ツール呼び出し前のコメントを投稿
            self._post_tool_call_before_comment(name, args)

            # Check if this is a command-executor tool
            if mcp_server == "command-executor":
                # Handle command execution through ExecutionEnvironmentManager
                if self.execution_manager is None:
                    error_msg = "Execution environment not available"
                    self.logger.error(error_msg)
                    self.llm_client.send_function_result(name, f"error: {error_msg}")
                    return False

                try:
                    # Execute command through execution manager
                    if tool_name == "execute_command":
                        result = self.execution_manager.execute_command(
                            command=args.get("command", ""),
                            working_directory=args.get("working_directory"),
                        )
                    else:
                        error_msg = f"Unknown command-executor tool: {tool_name}"
                        raise ValueError(error_msg)

                    # Reset error count on success
                    if error_state["last_tool"] == tool_name:
                        error_state["tool_error_count"] = 0

                    # Send result back to LLM
                    self.llm_client.send_function_result(name, json.dumps(result, ensure_ascii=False))

                    # ツール完了コメントを投稿（成功）
                    self._post_tool_call_after_comment(name, success=True)

                    return False

                except Exception as e:
                    error_msg = str(e)
                    self.logger.exception("Command execution failed: %s", error_msg)

                    # ツール完了コメントを投稿（失敗）
                    self._post_tool_call_after_comment(name, success=False)
                    # ツールエラーコメントを投稿
                    self._post_tool_error_comment(name, error_msg, task_id)

                    # Update error count
                    if error_state["last_tool"] == tool_name:
                        error_state["tool_error_count"] += 1
                    else:
                        error_state["tool_error_count"] = 1
                        error_state["last_tool"] = tool_name

                    # Send error result to LLM
                    self.llm_client.send_function_result(name, f"error: {error_msg}")

                    # Check if we should abort
                    if error_state["tool_error_count"] >= MAX_CONSECUTIVE_TOOL_ERRORS:
                        self.task.comment(
                            f"同じツール({name})で{MAX_CONSECUTIVE_TOOL_ERRORS}回連続エラーが発生したため処理を中止します。",
                        )
                        return True

                    return False

            # Execute the tool through MCP client
            try:
                result = self.mcp_clients[mcp_server].call_tool(tool_name, args)

                # Reset error count on success
                if error_state["last_tool"] == tool_name:
                    error_state["tool_error_count"] = 0

                # Send result back to LLM
                self.llm_client.send_function_result(name, str(result))

                # ツール完了コメントを投稿（成功）
                self._post_tool_call_after_comment(name, success=True)

                return False

            except Exception as e:
                # Handle tool execution error
                error_msg = str(e)
                if hasattr(e, "exceptions") and e.exceptions:
                    # Handle ExceptionGroup structure
                    if hasattr(e.exceptions[0], "exceptions"):
                        error_msg = str(e.exceptions[0].exceptions[0])
                    else:
                        error_msg = str(e.exceptions[0])

                self.logger.exception("Tool execution failed: %s", error_msg)

                # ツール完了コメントを投稿（失敗）
                self._post_tool_call_after_comment(name, success=False)
                # ツールエラーコメントを投稿
                self._post_tool_error_comment(name, error_msg, task_id)

                # Update error count
                if error_state["last_tool"] == tool_name:
                    error_state["tool_error_count"] += 1
                else:
                    error_state["tool_error_count"] = 1
                    error_state["last_tool"] = tool_name

                # Send error result to LLM
                self.llm_client.send_function_result(name, f"error: {error_msg}")

                # Check if we should abort
                if error_state["tool_error_count"] >= MAX_CONSECUTIVE_TOOL_ERRORS:
                    self.task.comment(
                        f"同じツール({name})で{MAX_CONSECUTIVE_TOOL_ERRORS}回連続エラーが発生したため処理を中止します。",
                    )
                    return True

                return False

        except Exception as e:
            self.logger.exception("Function call execution failed: %s", e)
            return False

    def _should_reflect(self, result: dict[str, Any]) -> bool:
        """Determine if reflection is needed.
        
        Args:
            result: Result from action execution
            
        Returns:
            True if reflection should be performed
        """
        # Reflect on error
        if result.get("status") == "error":
            return True

        # Reflect at configured intervals
        reflection_config = self.config.get("reflection", {})
        if not reflection_config.get("enabled", True):
            return False

        interval = reflection_config.get("trigger_interval", 3)
        # Only reflect at intervals after at least one action has been executed
        if interval > 0 and self.action_counter > 0 and self.action_counter % interval == 0:
            return True

        return False

    def _execute_reflection_phase(self, result: dict[str, Any]) -> dict[str, Any] | None:
        """Execute reflection on the result.
        
        Args:
            result: Result to reflect on
            
        Returns:
            Reflection dictionary or None if reflection failed
        """
        try:
            # Build reflection prompt
            reflection_prompt = self._build_reflection_prompt(result)

            # Get reflection from LLM
            self.llm_client.send_user_message(reflection_prompt)
            response, _, tokens = self.llm_client.get_response()  # Unpack tuple with tokens
            self.logger.info("Reflection LLM response (tokens: %d)", tokens)

            # トークン数を記録
            self.context_manager.update_statistics(llm_calls=1, tokens=tokens)

            # Parse reflection
            reflection = self._parse_reflection_response(response)

            # LLM呼び出し完了コメントを投稿
            self._post_llm_call_comment("reflection", reflection)

            # Save reflection
            if reflection:
                self.history_store.save_reflection(reflection)

            return reflection

        except Exception as e:
            self.logger.exception(f"Reflection phase failed: {e}")
            # LLMエラーコメントを投稿
            self._post_llm_error_comment("reflection", str(e))
            return None

    def _revise_plan(self, reflection: dict[str, Any]) -> dict[str, Any] | None:
        """Revise the plan based on reflection.
        
        Args:
            reflection: Reflection result
            
        Returns:
            Revised plan or None if revision failed
        """
        try:
            # Check revision limit
            max_revisions = self.config.get("revision", {}).get("max_revisions", 3)

            if self.revision_counter >= max_revisions:
                self.logger.error("Maximum plan revisions exceeded")
                return None

            # Increment counter after check
            self.revision_counter += 1

            # Build revision prompt
            revision_prompt = self._build_revision_prompt(reflection)

            # Get revised plan from LLM
            self.llm_client.send_user_message(revision_prompt)
            response, _, tokens = self.llm_client.get_response()  # Unpack tuple with tokens
            self.logger.info("Plan revision LLM response (tokens: %d)", tokens)

            # トークン数を記録
            self.context_manager.update_statistics(llm_calls=1, tokens=tokens)

            # Parse revised plan
            revised_plan = self._parse_planning_response(response)

            # LLM呼び出し完了コメントを投稿
            self._post_llm_call_comment("revision", revised_plan)

            # Save revision
            if revised_plan:
                self.history_store.save_revision(revised_plan, reflection)

            return revised_plan

        except Exception as e:
            self.logger.exception("Plan revision failed")
            # LLMエラーコメントを投稿
            self._post_llm_error_comment("revision", str(e))
            return None

    def _request_execution_replan_decision(
        self,
        current_action: dict[str, Any],
        result: dict[str, Any],
    ) -> ReplanDecision:
        """実行フェーズでの再計画判断をLLMに依頼する.

        Args:
            current_action: 実行されたアクション
            result: 実行結果

        Returns:
            ReplanDecision インスタンス

        """
        if not self.replan_manager.enabled:
            return ReplanDecision()

        # 残りのアクションを取得
        remaining_actions = []
        if self.current_plan:
            action_plan = self.current_plan.get("action_plan", {})
            actions = action_plan.get("actions", [])
            remaining_actions = actions[self.action_counter:]

        # エラー情報を準備
        error_info = result.get("error", "") if result.get("status") == "error" else ""

        # コンテキストを構築
        context = {
            "executed_action": current_action,
            "execution_result": result,
            "error_info": error_info,
            "completed_count": self.action_counter,
            "total_count": len(self.current_plan.get("action_plan", {}).get("actions", [])),
            "error_count": self.error_count,
            "consecutive_errors": self.consecutive_errors,
            "remaining_actions": remaining_actions,
        }

        # LLMに再計画判断を依頼
        decision = self.replan_manager.request_llm_decision(
            self.llm_client,
            TargetPhase.EXECUTION.value,
            context,
        )

        return decision

    def _handle_replan(self, decision: ReplanDecision) -> bool:
        """再計画を実行する.

        Args:
            decision: LLMの再計画判断

        Returns:
            再計画が実行された場合True

        """
        if not decision.replan_needed:
            return False

        # 再計画を実行可能かチェック
        if not self.replan_manager.execute_replan(decision, self.current_phase):
            return False

        # 再計画通知をIssue/MRに投稿
        self._post_replan_notification(decision)

        # 再計画タイプに応じた処理
        replan_type = decision.replan_type
        target_phase = decision.target_phase

        if replan_type == ReplanType.RETRY.value:
            # リトライ: アクションカウンターを1つ戻す
            if self.action_counter > 0:
                self.action_counter -= 1
            self.consecutive_errors = 0
            return True

        if replan_type == ReplanType.PARTIAL_REPLAN.value:
            # 部分再計画: 残りのアクションを再生成
            self._execute_partial_replan(decision)
            return True

        if replan_type in (
            ReplanType.FULL_REPLAN.value,
            ReplanType.ACTION_REGENERATION.value,
        ):
            # 完全再計画またはアクション再生成
            self._execute_full_replan(decision)
            return True

        if replan_type == ReplanType.TASK_REDECOMPOSITION.value:
            # タスク再分解: 計画フェーズから再実行
            self._execute_task_redecomposition(decision)
            return True

        if replan_type == ReplanType.GOAL_REVISION.value:
            # 目標再確認: 最初から再実行
            self._execute_goal_revision(decision)
            return True

        return False

    def _post_replan_notification(self, decision: ReplanDecision) -> None:
        """再計画判断の通知をIssue/MRに投稿する.

        Args:
            decision: LLMの再計画判断

        """
        # ユーザー確認が必要な場合
        if decision.clarification_needed and decision.clarification_questions:
            questions_str = "\n".join(
                f"{i}. {q}" for i, q in enumerate(decision.clarification_questions, 1)
            )
            assumptions_str = ""
            if decision.assumptions_to_make:
                assumptions_str = (
                    "\n\n**If no response**:\n"
                    "I will proceed with the following assumptions:\n"
                    + "\n".join(f"- {a}" for a in decision.assumptions_to_make)
                )

            comment = f"""## ❓ Clarification Needed (AI Decision)

I've analyzed the task and need some clarification to proceed effectively:

**Questions**:
{questions_str}

**Context**:
{decision.reasoning}{assumptions_str}

Please reply to this comment with your answers."""
            if hasattr(self.task, "comment"):
                self.task.comment(comment)
            return

        # 通常の再計画通知
        issues_str = ""
        if decision.issues_found:
            issues_str = "\n**Issues Found**:\n" + "\n".join(
                f"- {issue}" for issue in decision.issues_found
            )

        actions_str = ""
        if decision.recommended_actions:
            actions_str = "\n\n**Recommended Actions**:\n" + "\n".join(
                f"- {action}" for action in decision.recommended_actions
            )

        comment = f"""## 🔄 Plan Revision Decided by AI

**Phase**: {self.current_phase}
**Confidence**: {decision.confidence * 100:.0f}%
**Replan Type**: {decision.replan_type}
**Target Phase**: {decision.target_phase}

**Reasoning**:
{decision.reasoning}{issues_str}{actions_str}

*{datetime.now().strftime(DATETIME_FORMAT)}*"""

        if hasattr(self.task, "comment"):
            self.task.comment(comment)

    def _execute_partial_replan(self, decision: ReplanDecision) -> None:
        """部分再計画を実行する.

        Args:
            decision: LLMの再計画判断

        """
        self.logger.info("部分再計画を実行します")

        # 完了済みアクションを保持しつつ、残りのアクションを再生成
        if self.current_plan:
            completed_actions = self.current_plan.get("action_plan", {}).get(
                "actions", [],
            )[: self.action_counter]

            # LLMに残りのアクションの再生成を依頼
            remaining_prompt = self._build_partial_replan_prompt(
                completed_actions, decision,
            )
            self.llm_client.send_user_message(remaining_prompt)
            response, _, tokens = self.llm_client.get_response()
            self.context_manager.update_statistics(llm_calls=1, tokens=tokens)

            # 新しいアクションをパース
            new_plan = self._parse_planning_response(response)
            if new_plan and new_plan.get("action_plan", {}).get("actions"):
                # 完了済みアクションと新しいアクションをマージ
                new_actions = new_plan["action_plan"]["actions"]
                self.current_plan["action_plan"]["actions"] = (
                    completed_actions + new_actions
                )
                self.plan_revision_number += 1

                # チェックリストを更新
                self._update_checklist_on_replan(decision)

    def _execute_full_replan(self, decision: ReplanDecision) -> None:
        """完全再計画を実行する.

        Args:
            decision: LLMの再計画判断

        """
        self.logger.info("完全再計画を実行します")

        # 完了済みアクションを保持
        completed_count = self.action_counter
        completed_actions = []
        if self.current_plan:
            completed_actions = self.current_plan.get("action_plan", {}).get(
                "actions", [],
            )[:completed_count]

        # 新しい計画を生成
        new_plan = self._execute_planning_phase()
        if new_plan:
            self.current_plan = new_plan
            self.history_store.save_plan(new_plan)
            self.plan_revision_number += 1

            # チェックリストを更新
            self._update_checklist_on_replan(decision, completed_actions)

    def _execute_task_redecomposition(self, decision: ReplanDecision) -> None:
        """タスク再分解を実行する.

        Args:
            decision: LLMの再計画判断

        """
        self.logger.info("タスク再分解を実行します")

        # アクションカウンターをリセット
        self.action_counter = 0
        self.error_count = 0
        self.consecutive_errors = 0
        self.plan_revision_number += 1

        # 新しい計画を生成
        new_plan = self._execute_planning_phase()
        if new_plan:
            self.current_plan = new_plan
            self.history_store.save_plan(new_plan)

            # チェックリストを更新
            self._update_checklist_on_replan(decision)

    def _execute_goal_revision(self, decision: ReplanDecision) -> None:
        """目標再確認を実行する.

        Args:
            decision: LLMの再計画判断

        """
        self.logger.info("目標再確認を実行します")

        # すべてをリセット
        self.action_counter = 0
        self.revision_counter = 0
        self.error_count = 0
        self.consecutive_errors = 0
        self.plan_revision_number += 1
        self.replan_manager.reset_counts()

        # 新しい計画を生成
        new_plan = self._execute_planning_phase()
        if new_plan:
            self.current_plan = new_plan
            self.history_store.save_plan(new_plan)

            # チェックリストを更新
            self._update_checklist_on_replan(decision)

    def _build_partial_replan_prompt(
        self,
        completed_actions: list[dict[str, Any]],
        decision: ReplanDecision,
    ) -> str:
        """部分再計画用のプロンプトを生成する.

        Args:
            completed_actions: 完了済みアクション
            decision: LLMの再計画判断

        Returns:
            プロンプト文字列

        """
        completed_str = json.dumps(completed_actions, indent=2, ensure_ascii=False)
        issues_str = "\n".join(f"- {issue}" for issue in decision.issues_found)

        return f"""The following actions have been completed:
{completed_str}

However, we encountered issues and need to replan the remaining actions:

**Issues Found**:
{issues_str}

**Reason for Replanning**:
{decision.reasoning}

Please generate new actions to complete the remaining work.
Maintain the same JSON format as before for action_plan.actions."""

    def _update_checklist_on_replan(
        self,
        decision: ReplanDecision,
        completed_actions: list[dict[str, Any]] | None = None,
    ) -> None:
        """再計画時にチェックリストを更新する.

        Args:
            decision: LLMの再計画判断
            completed_actions: 完了済みアクション(オプション)

        """
        if not self.current_plan:
            return

        action_plan = self.current_plan.get("action_plan", {})
        actions = action_plan.get("actions", [])

        if not actions:
            return

        # チェックリストを構築
        checklist_lines = [
            f"## 📋 Execution Plan (Revised #{self.plan_revision_number})",
            "",
            f"**Revision Reason**: {decision.reasoning[:100]}...",
            "",
            f"**Previous Progress**: {self.action_counter}/{len(actions)} completed",
            "",
            "### New Plan:",
        ]

        for i, action in enumerate(actions):
            task_id = action.get("task_id", f"task_{i + 1}")
            purpose = action.get("purpose", "Execute action")

            # 完了済みかどうかを判定
            checkbox = "[x]" if i < self.action_counter else "[ ]"
            checklist_lines.append(f"- {checkbox} **{task_id}**: {purpose}")

        checklist_lines.append("")
        progress_pct = (
            int(self.action_counter / len(actions) * 100) if actions else 0
        )
        checklist_lines.append(
            f"*Progress: {self.action_counter}/{len(actions)} ({progress_pct}%) complete "
            f"| Revision: #{self.plan_revision_number} "
            f"at {datetime.now().strftime(DATETIME_FORMAT)}*",
        )

        checklist_content = "\n".join(checklist_lines)

        # 既存のコメントを更新または新規投稿
        if self.checklist_comment_id and hasattr(self.task, "update_comment"):
            self.task.update_comment(self.checklist_comment_id, checklist_content)
            self.logger.info(
                "再計画時にチェックリストを更新しました (comment_id=%s)",
                self.checklist_comment_id,
            )
        elif hasattr(self.task, "comment"):
            result = self.task.comment(checklist_content)
            if isinstance(result, dict):
                self.checklist_comment_id = result.get("id")
            self.logger.info("再計画時に新しいチェックリストを投稿しました")

    def _is_complete(self) -> bool:
        """Check if task is complete.
        
        Returns:
            True if task is complete
        """
        if not self.current_plan:
            return False

        # Check if all actions are executed
        action_plan = self.current_plan.get("action_plan", {})
        actions = action_plan.get("actions", [])

        return self.action_counter >= len(actions)

    def _build_planning_prompt(self, past_history: list[dict[str, Any]]) -> str:
        """Build prompt for planning phase.
        
        Args:
            past_history: Past execution history
            
        Returns:
            Planning prompt string
        """
        # Get task information including comments/discussions
        task_info = self.task.get_prompt()

        prompt_parts = [
            "Create a comprehensive plan for the following task:",
            "",
            task_info,  # This includes issue/MR details and all comments
            "",
        ]

        # 計画前情報収集フェーズの結果を追加
        if self.pre_planning_result:
            pre_planning = self.pre_planning_result.get("pre_planning_result", {})

            # 理解した依頼内容のサマリー
            request_understanding = pre_planning.get("request_understanding", {})
            if request_understanding:
                prompt_parts.extend([
                    "=== 依頼内容の理解（計画前情報収集フェーズで分析済み） ===",
                    f"タスク種別: {request_understanding.get('task_type', '不明')}",
                    f"主な目標: {request_understanding.get('primary_goal', '不明')}",
                    f"理解の確信度: {request_understanding.get('understanding_confidence', 0):.0%}",
                    "",
                ])

                # 成果物
                deliverables = request_understanding.get("expected_deliverables", [])
                if deliverables:
                    prompt_parts.append("期待される成果物:")
                    for d in deliverables:
                        prompt_parts.append(f"  - {d}")
                    prompt_parts.append("")

                # 制約
                constraints = request_understanding.get("constraints", [])
                if constraints:
                    prompt_parts.append("制約条件:")
                    for c in constraints:
                        prompt_parts.append(f"  - {c}")
                    prompt_parts.append("")

                # スコープ
                scope = request_understanding.get("scope", {})
                if scope:
                    in_scope = scope.get("in_scope", [])
                    out_of_scope = scope.get("out_of_scope", [])
                    if in_scope:
                        prompt_parts.append(f"スコープ内: {', '.join(in_scope)}")
                    if out_of_scope:
                        prompt_parts.append(f"スコープ外: {', '.join(out_of_scope)}")
                    prompt_parts.append("")

                # 曖昧な点と選択した解釈
                ambiguities = request_understanding.get("ambiguities", [])
                if ambiguities:
                    prompt_parts.append("曖昧な点と選択した解釈:")
                    for amb in ambiguities:
                        # ambが辞書か文字列かを判定
                        if isinstance(amb, dict):
                            item = amb.get("item", "")
                            selected = amb.get("selected_interpretation", "")
                            reasoning = amb.get("reasoning", "")
                            prompt_parts.append(f"  - {item}: {selected} (理由: {reasoning})")
                        elif isinstance(amb, str):
                            # 文字列の場合はそのまま使用
                            prompt_parts.append(f"  - {amb}")
                    prompt_parts.append("")

            # 収集した情報
            collected_info = pre_planning.get("collected_information", {})
            if collected_info:
                prompt_parts.append("=== 収集した情報 ===")
                for category, info in collected_info.items():
                    if info:
                        prompt_parts.append(f"{category}:")
                        # JSON構造を保持するため、truncationは避け、要約形式で表示
                        json_str = json.dumps(info, indent=2, ensure_ascii=False)
                        if len(json_str) > JSON_TRUNCATION_LIMIT:
                            prompt_parts.append(f"{json_str[:JSON_TRUNCATION_LIMIT]}... (省略)")
                        else:
                            prompt_parts.append(json_str)
                        prompt_parts.append("")

            # 推測した内容
            assumptions = pre_planning.get("assumptions", [])
            if assumptions:
                prompt_parts.append("=== 推測した内容（収集できなかった情報）===")
                for assumption in assumptions:
                    info_id = assumption.get("info_id", "")
                    value = assumption.get("assumed_value", "")
                    confidence = assumption.get("confidence", 0)
                    prompt_parts.append(f"  - {info_id}: {value} (確信度: {confidence:.0%})")
                prompt_parts.append("")

            # 情報ギャップ
            gaps = pre_planning.get("information_gaps", [])
            if gaps:
                prompt_parts.append("=== 情報ギャップ（収集も推測もできなかった情報）===")
                for gap in gaps:
                    desc = gap.get("description", "")
                    impact = gap.get("impact", "")
                    prompt_parts.append(f"  - {desc} (影響: {impact})")
                prompt_parts.append("")

            # 計画への推奨事項
            recommendations = pre_planning.get("recommendations_for_planning", [])
            if recommendations:
                prompt_parts.append("=== 計画時の推奨事項 ===")
                for rec in recommendations:
                    prompt_parts.append(f"  - {rec}")
                prompt_parts.append("")

        # 実行環境選択情報を追加
        environment_selection_prompt = self._build_environment_selection_prompt()
        prompt_parts.append(environment_selection_prompt)

        prompt_parts.extend([
            "IMPORTANT - Task Complexity Assessment:",
            "Before creating your plan, evaluate the task complexity:",
            "- Simple (1-2 tool calls): Single file creation/modification, basic operations → Use 1-3 subtasks",
            "- Medium (3-6 tool calls): Multiple related changes, small features → Use 3-6 subtasks",
            "- Complex (7+ tool calls): Major features, large refactoring → Use 6-10 subtasks maximum",
            "",
            "Default to SIMPLER plans. Most tasks are simpler than they appear.",
            "Combine related operations. Don't over-decompose simple tasks.",
        ])

        if past_history:
            prompt_parts.extend([
                "",
                "Past execution history for this issue:",
                json.dumps(past_history, indent=2),
            ])

        prompt_parts.extend([
            "",
            "Please provide a plan in the following JSON format:",
            "{",
            '  "goal_understanding": {...},',
            '  "task_decomposition": {...},',
            '  "action_plan": {...},',
            '  "selected_environment": {',
            '    "name": "python",',
            '    "reasoning": "選択理由..."',
            '  }',
            "}",
        ])

        return "\n".join(prompt_parts)

    def _build_environment_selection_prompt(self) -> str:
        """実行環境選択プロンプトを構築する.

        利用可能な環境リストと選択指示を含むプロンプトを生成します。

        Returns:
            環境選択プロンプト文字列

        """
        # ExecutionEnvironmentManagerから環境リストを取得（利用可能な場合）
        environments = {}
        default_env = "python"

        if self.execution_manager is not None:
            environments = self.execution_manager.get_available_environments()
            default_env = self.execution_manager.get_default_environment()
        else:
            # デフォルトの環境リスト
            environments = {
                "python": "coding-agent-executor-python:latest",
                "miniforge": "coding-agent-executor-miniforge:latest",
                "node": "coding-agent-executor-node:latest",
                "java": "coding-agent-executor-java:latest",
                "go": "coding-agent-executor-go:latest",
            }

        # 環境ごとの推奨用途
        env_recommendations = {
            "python": "Pure Python projects, Django/Flask web frameworks, data processing scripts",
            "miniforge": "Data science, scientific computing, NumPy/pandas/scikit-learn, conda environments (condaenv.yaml, environment.yml)",
            "node": "JavaScript/TypeScript, React/Vue/Angular, Node.js backend (Express, NestJS)",
            "java": "Java/Kotlin, Spring Boot, Quarkus, Maven/Gradle projects",
            "go": "Go projects, CLI tools, microservices",
        }

        prompt_lines = [
            "",
            "## Execution Environment Selection",
            "",
            "You must select an appropriate execution environment for this task. The following environments are available:",
            "",
            "| Environment | Image | Recommended For |",
            "|-------------|-------|-----------------|",
        ]

        for env_name, image in environments.items():
            recommendation = env_recommendations.get(env_name, "General purpose")
            prompt_lines.append(f"| {env_name} | {image} | {recommendation} |")

        prompt_lines.extend([
            "",
            f"**Default Environment**: {default_env}",
            "",
            "**Selection Criteria:**",
            "- Check the project's dependency files (requirements.txt, package.json, go.mod, pom.xml, condaenv.yaml, environment.yml)",
            "- Consider the main programming language of the task",
            "- For data science projects with conda environments, select 'miniforge'",
            "- For pure Python projects without conda, select 'python'",
            "",
            "Include your selection in the response with 'selected_environment' field:",
            '  "selected_environment": {',
            '    "name": "environment_name",',
            '    "reasoning": "Why this environment was selected"',
            '  }',
            "",
        ])

        return "\n".join(prompt_lines)

    def _build_action_prompt(self, action: dict[str, Any]) -> str:
        """Build prompt for action execution.
        
        Args:
            action: Action to execute
            
        Returns:
            Action prompt string
        """
        # Extract tool information from action
        tool_name = action.get("tool", "unknown")
        parameters = action.get("parameters", {})
        purpose = action.get("purpose", "")

        prompt_parts = [
            f"Execute the following action using the `{tool_name}` tool:",
            "",
            f"**Purpose**: {purpose}",
            "",
            "**Tool Parameters**:",
            json.dumps(parameters, indent=2, ensure_ascii=False),
            "",
            "Please use function calling to execute this tool with the exact parameters provided above.",
        ]

        return "\n".join(prompt_parts)

    def _build_reflection_prompt(self, result: dict[str, Any]) -> str:
        """Build prompt for reflection.
        
        Args:
            result: Result to reflect on
            
        Returns:
            Reflection prompt string
        """
        return f"Reflect on the following result:\n{json.dumps(result, indent=2)}\n\nProvide evaluation and determine if plan revision is needed."

    def _build_revision_prompt(self, reflection: dict[str, Any]) -> str:
        """Build prompt for plan revision.
        
        Args:
            reflection: Reflection result
            
        Returns:
            Revision prompt string
        """
        return f"Revise the plan based on:\n{json.dumps(reflection, indent=2)}\n\nProvide a revised plan."

    def _parse_planning_response(self, response: str) -> dict[str, Any] | None:
        """Parse planning response from LLM.
        
        Args:
            response: LLM response string
            
        Returns:
            Parsed plan dictionary or None if parsing failed
        """
        try:
            # Try to extract JSON from response
            if isinstance(response, dict):
                return response

            # Remove <think></think> tags if present
            response = re.sub(r"<think>.*?</think>", "", response, flags=re.DOTALL)
            response = response.strip()

            # Log the response for debugging
            self.logger.debug("Planning response: %s", response[:500])

            # Try to parse as JSON
            try:
                return json.loads(response)
            except json.JSONDecodeError:
                # Try to extract JSON from markdown code blocks
                json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group(1))

                # Try to find JSON object in text
                json_match = re.search(r"\{.*\}", response, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group(0))

                raise

        except (json.JSONDecodeError, AttributeError):
            self.logger.warning("Failed to parse planning response as JSON. Response: %s", response[:200])
            return None

    def _parse_reflection_response(self, response: str) -> dict[str, Any] | None:
        """Parse reflection response from LLM.
        
        Args:
            response: LLM response string
            
        Returns:
            Parsed reflection dictionary or None if parsing failed
        """
        try:
            if isinstance(response, dict):
                return response

            # Remove <think></think> tags if present
            response = re.sub(r"<think>.*?</think>", "", response, flags=re.DOTALL)
            response = response.strip()

            # Try to parse as JSON
            try:
                return json.loads(response)
            except json.JSONDecodeError:
                # Try to extract JSON from markdown code blocks or text
                json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group(1))

                json_match = re.search(r"\{.*\}", response, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group(0))

                raise

        except (json.JSONDecodeError, AttributeError):
            self.logger.warning("Failed to parse reflection response as JSON. Response: %s", response[:200])
            return None

    def _post_plan_as_checklist(self, plan: dict[str, Any]) -> None:
        """Post the plan as a markdown checklist to Issue/MR.
        
        Args:
            plan: The plan to post
        """
        try:
            # Extract actions from the plan
            action_plan = plan.get("action_plan", {})
            actions = action_plan.get("actions", [])

            if not actions:
                self.logger.warning("No actions found in plan, skipping checklist posting")
                return

            # Build markdown checklist
            checklist_lines = ["## 📋 Execution Plan", ""]

            for i, action in enumerate(actions, 1):
                task_id = action.get("task_id", f"task_{i}")
                purpose = action.get("purpose", "Execute action")
                checklist_lines.append(f"- [ ] **{task_id}**: {purpose}")

            checklist_lines.append("")
            checklist_lines.append("*Progress will be updated as tasks complete.*")

            checklist_content = "\n".join(checklist_lines)

            # Post to Issue/MR using task's comment method and save comment ID
            if hasattr(self.task, "comment"):
                result = self.task.comment(checklist_content)
                # Extract comment ID from result if available
                if isinstance(result, dict):
                    # GitLab: {"id": ...}, GitHub: {"id": ...}
                    self.checklist_comment_id = result.get("id")
                self.logger.info("Posted execution plan checklist to Issue/MR (comment_id=%s)", self.checklist_comment_id)
            else:
                self.logger.warning("Task does not support comment, cannot post checklist")

        except Exception as e:
            self.logger.error("Failed to post plan as checklist: %s", str(e))

    def _update_checklist_progress(self, completed_action_index: int) -> None:
        """Update the checklist to mark a task as complete.
        
        Args:
            completed_action_index: Index of the completed action (0-based)
        """
        try:
            if not self.current_plan:
                return

            action_plan = self.current_plan.get("action_plan", {})
            actions = action_plan.get("actions", [])

            if completed_action_index >= len(actions):
                return

            # Build updated checklist
            checklist_lines = ["## 📋 Execution Plan", ""]

            for i, action in enumerate(actions, 1):
                task_id = action.get("task_id", f"task_{i}")
                purpose = action.get("purpose", "Execute action")

                # Mark completed actions with [x]
                checkbox = "[x]" if i <= completed_action_index + 1 else "[ ]"
                checklist_lines.append(f"- {checkbox} **{task_id}**: {purpose}")

            checklist_lines.append("")
            progress_pct = int((completed_action_index + 1) / len(actions) * 100)
            checklist_lines.append(f"*Progress: {completed_action_index + 1}/{len(actions)} ({progress_pct}%) complete*")

            checklist_content = "\n".join(checklist_lines)

            # Update the existing comment instead of posting a new one
            if self.checklist_comment_id and hasattr(self.task, "update_comment"):
                self.task.update_comment(self.checklist_comment_id, checklist_content)
                self.logger.info("Updated checklist progress (comment_id=%s)", self.checklist_comment_id)
            elif hasattr(self.task, "comment"):
                # Fallback: post new comment if update not supported
                result = self.task.comment(checklist_content)
                if isinstance(result, dict):
                    self.checklist_comment_id = result.get("id")
                self.logger.info("Posted new checklist progress comment")

        except Exception as e:
            self.logger.error("Failed to update checklist progress: %s", str(e))

    def _mark_checklist_complete(self) -> None:
        """Mark all checklist items as complete."""
        try:
            if not self.current_plan:
                return

            action_plan = self.current_plan.get("action_plan", {})
            actions = action_plan.get("actions", [])

            # Build completed checklist
            checklist_lines = ["## 📋 Execution Plan", ""]

            for i, action in enumerate(actions, 1):
                task_id = action.get("task_id", f"task_{i}")
                purpose = action.get("purpose", "Execute action")
                checklist_lines.append(f"- [x] **{task_id}**: {purpose}")

            checklist_lines.append("")
            checklist_lines.append(f"*✅ All {len(actions)} tasks completed successfully!*")

            checklist_content = "\n".join(checklist_lines)

            # Update the existing comment instead of posting a new one
            if self.checklist_comment_id and hasattr(self.task, "update_comment"):
                self.task.update_comment(self.checklist_comment_id, checklist_content)
                self.logger.info("Marked checklist complete (comment_id=%s)", self.checklist_comment_id)
            elif hasattr(self.task, "comment"):
                # Fallback: post new comment if update not supported
                result = self.task.comment(checklist_content)
                if isinstance(result, dict):
                    self.checklist_comment_id = result.get("id")
                self.logger.info("Posted new completion checklist comment")

        except Exception as e:
            self.logger.error("Failed to mark checklist complete: %s", str(e))

    def _execute_verification_phase(self) -> dict[str, Any] | None:
        """検証フェーズを実行する.

        すべての計画アクション完了後に実行され、実装の完全性を検証します。
        プレースホルダの検出、成功基準の達成度チェックを行います。

        Returns:
            検証結果の辞書、またはパース失敗時はNone

        """
        try:
            # 検証プロンプトを構築
            verification_prompt = self._build_verification_prompt()

            # LLMに検証を依頼
            self.llm_client.send_user_message(verification_prompt)
            response, functions, tokens = self.llm_client.get_response()
            self.logger.info("Verification phase LLM response (tokens: %d)", tokens)

            # トークン数を記録
            self.context_manager.update_statistics(llm_calls=1, tokens=tokens)

            # 検証のためにツールを使用する可能性があるため、function callsを処理
            error_state = {"last_tool": None, "tool_error_count": 0}
            if functions:
                if not isinstance(functions, list):
                    functions = [functions]
                for function in functions:
                    self._execute_function_call(function, error_state)

                # ツール実行後の追加応答を取得
                response, _, additional_tokens = self.llm_client.get_response()
                tokens += additional_tokens
                self.context_manager.update_statistics(llm_calls=1, tokens=additional_tokens)

            # 検証結果をパース
            verification_result = self._parse_planning_response(response)

            # LLM呼び出し完了コメントを投稿
            self._post_llm_call_comment("verification", verification_result)

            # 検証結果を履歴に保存
            if verification_result:
                self.history_store.save_verification(verification_result)

            return verification_result

        except Exception as e:
            self.logger.exception("Verification phase execution failed")
            # LLMエラーコメントを投稿
            self._post_llm_error_comment("verification", str(e))
            return None

    def _build_verification_prompt(self) -> str:
        """検証フェーズ用のプロンプトを構築する.

        Returns:
            検証プロンプト文字列

        """
        # 実行済みアクションのサマリー
        executed_actions_summary = self._build_executed_actions_summary()

        # 成功基準を抽出
        success_criteria = self._extract_success_criteria()

        prompt_parts = [
            "## Verification Phase",
            "",
            "All planned actions have been executed. Now verify the implementation completeness.",
            "",
            "### Executed Actions Summary",
            executed_actions_summary,
            "",
            "### Success Criteria",
            success_criteria,
            "",
            "### Implementation Completeness Checklist",
            "Please verify the following:",
            "1. All functions/methods are fully implemented (no placeholders)",
            "2. All code paths are complete",
            "3. All required features from the task are implemented",
            "4. Tests (if required) are implemented and pass",
            "5. Documentation (if required) is complete",
            "",
            "### Placeholder Detection",
            "Search for the following placeholder patterns in the modified files:",
            "- TODO",
            "- FIXME",
            "- '...'",
            "- '# implementation here'",
            "- 'pass' statements that should have implementation",
            "- 'raise NotImplementedError'",
            "",
            "**IMPORTANT**: Use file reading tools to re-read the modified files and verify the implementation.",
            "",
            "### Response Format",
            "Provide your verification result in the following JSON format:",
            "```json",
            "{",
            '  "phase": "verification",',
            '  "verification_passed": true/false,',
            '  "issues_found": ["issue1", "issue2"],',
            '  "placeholder_detected": {',
            '    "count": 0,',
            '    "locations": []',
            "  },",
            '  "additional_work_needed": true/false,',
            '  "additional_actions": [',
            "    {",
            '      "task_id": "verification_fix_1",',
            '      "action_type": "tool_call",',
            '      "tool": "tool_name",',
            '      "parameters": {},',
            '      "purpose": "Fix incomplete implementation",',
            '      "expected_outcome": "Fully implemented feature"',
            "    }",
            "  ],",
            '  "completion_confidence": 0.95,',
            '  "comment": "Summary of verification result"',
            "}",
            "```",
        ]

        return "\n".join(prompt_parts)

    def _build_executed_actions_summary(self) -> str:
        """実行済みアクションのサマリーを作成する.

        Returns:
            実行済みアクションのサマリー文字列

        """
        if not self.current_plan:
            return "No plan available."

        action_plan = self.current_plan.get("action_plan", {})
        actions = action_plan.get("actions", [])

        if not actions:
            return "No actions were executed."

        summary_lines = []
        for i, action in enumerate(actions, 1):
            task_id = action.get("task_id", f"task_{i}")
            purpose = action.get("purpose", "Execute action")
            tool = action.get("tool", "unknown")
            summary_lines.append(f"- **{task_id}** ({tool}): {purpose}")

        return "\n".join(summary_lines)

    def _extract_success_criteria(self) -> str:
        """current_planから成功基準を抽出する.

        Returns:
            成功基準の文字列

        """
        if not self.current_plan:
            return "No success criteria available (no plan)."

        goal_understanding = self.current_plan.get("goal_understanding", {})
        success_criteria = goal_understanding.get("success_criteria", [])

        if not success_criteria:
            return "No explicit success criteria defined in the plan."

        if isinstance(success_criteria, list):
            criteria_lines = [f"- {criterion}" for criterion in success_criteria]
            return "\n".join(criteria_lines)
        return str(success_criteria)

    def _post_verification_result(self, verification_result: dict[str, Any]) -> None:
        """検証結果をIssue/MRにコメントとして投稿する.

        Args:
            verification_result: 検証結果の辞書

        """
        try:
            verification_passed = verification_result.get("verification_passed", False)
            issues_found = verification_result.get("issues_found", [])
            placeholder_info = verification_result.get("placeholder_detected", {})
            additional_actions = verification_result.get("additional_actions", [])
            confidence = verification_result.get("completion_confidence", 0)
            comment = verification_result.get("comment", "")

            # 絵文字を決定
            emoji = "✅" if verification_passed else "⚠️"

            # コメントを構築
            comment_lines = [
                f"## 🔍 Verification Result - {emoji}",
                "",
                f"**Status**: {'Passed' if verification_passed else 'Issues Found'}",
                f"**Confidence**: {confidence * 100:.0f}%",
                "",
            ]

            # 検出された問題
            if issues_found:
                comment_lines.append("### Issues Found")
                for issue in issues_found:
                    comment_lines.append(f"- {issue}")
                comment_lines.append("")

            # プレースホルダ検出
            placeholder_count = placeholder_info.get("count", 0)
            if placeholder_count > 0:
                comment_lines.append(f"### Placeholder Detection: {placeholder_count} found")
                locations = placeholder_info.get("locations", [])
                for loc in locations:
                    comment_lines.append(f"- {loc}")
                comment_lines.append("")

            # 追加作業
            if additional_actions:
                comment_lines.append(f"### Additional Work Needed: {len(additional_actions)} actions")
                for action in additional_actions:
                    task_id = action.get("task_id", "unknown")
                    purpose = action.get("purpose", "")
                    comment_lines.append(f"- **{task_id}**: {purpose}")
                comment_lines.append("")

            # サマリーコメント
            if comment:
                comment_lines.append("### Summary")
                comment_lines.append(comment)
                comment_lines.append("")

            # タイムスタンプ
            timestamp = datetime.now().strftime(DATETIME_FORMAT)
            comment_lines.append(f"*{timestamp}*")

            comment_content = "\n".join(comment_lines)

            # Issue/MRに投稿
            if hasattr(self.task, "comment"):
                self.task.comment(comment_content)
                self.logger.info("Posted verification result to Issue/MR")
            else:
                self.logger.warning("Task does not support comment, cannot post verification result")

        except Exception as e:
            self.logger.error("Failed to post verification result: %s", str(e))

    def _update_checklist_for_additional_work(
        self,
        verification_result: dict[str, Any],
        additional_actions: list[dict[str, Any]],
    ) -> None:
        """追加作業用にチェックリストを更新する.

        元の計画(完了済み)と追加作業を明確に区別して表示します。

        Args:
            verification_result: 検証結果の辞書
            additional_actions: 追加アクションのリスト

        """
        try:
            if not self.current_plan:
                return

            action_plan = self.current_plan.get("action_plan", {})
            original_actions = action_plan.get("actions", [])

            # チェックリストを構築
            checklist_lines = [
                "## 📋 Execution Plan (Verification Round)",
                "",
                "### Original Plan (Completed)",
            ]

            # 元の計画(すべて完了)
            for i, action in enumerate(original_actions, 1):
                task_id = action.get("task_id", f"task_{i}")
                purpose = action.get("purpose", "Execute action")
                checklist_lines.append(f"- [x] **{task_id}**: {purpose}")

            checklist_lines.extend([
                "",
                "### Additional Work (From Verification)",
            ])

            # 追加作業(未完了)
            for i, action in enumerate(additional_actions, 1):
                task_id = action.get("task_id", f"verification_fix_{i}")
                purpose = action.get("purpose", "Fix issue")
                checklist_lines.append(f"- [ ] **{task_id}**: {purpose}")

            checklist_lines.append("")

            # 進捗情報
            total_actions = len(original_actions) + len(additional_actions)
            completed = len(original_actions)
            # total_actionsが0の場合は100%(完了)とする
            progress_pct = int(completed / total_actions * 100) if total_actions else 100
            checklist_lines.append(
                f"*Progress: {completed}/{total_actions} ({progress_pct}%) - "
                f"Verification found {len(additional_actions)} additional items*",
            )

            checklist_content = "\n".join(checklist_lines)

            # 既存のコメントを更新または新規投稿
            if self.checklist_comment_id and hasattr(self.task, "update_comment"):
                self.task.update_comment(self.checklist_comment_id, checklist_content)
                self.logger.info(
                    "Updated checklist for additional work (comment_id=%s)",
                    self.checklist_comment_id,
                )
            elif hasattr(self.task, "comment"):
                result = self.task.comment(checklist_content)
                if isinstance(result, dict):
                    self.checklist_comment_id = result.get("id")
                self.logger.info("Posted new checklist for additional work")

        except Exception as e:
            self.logger.error("Failed to update checklist for additional work: %s", str(e))

    def _load_planning_system_prompt(self) -> None:
        """Load and send the planning-specific system prompt to LLM client."""
        try:
            # Read system_prompt_planning.txt
            prompt_path = Path("system_prompt_planning.txt")

            if not prompt_path.exists():
                self.logger.warning("system_prompt_planning.txt not found, using default behavior")
                return

            with prompt_path.open("r", encoding="utf-8") as f:
                planning_prompt = f.read()

            # Get MCP client system prompts (function calling definitions)
            mcp_prompt = ""
            for client in self.mcp_clients.values():
                mcp_prompt += client.system_prompt + "\n"

            # Replace placeholder with MCP prompts
            planning_prompt = planning_prompt.replace("{mcp_prompt}", mcp_prompt)

            # プロジェクト固有のエージェントルールを読み込み
            project_rules = self._load_project_agent_rules()
            if project_rules:
                planning_prompt = planning_prompt + "\n" + project_rules
                self.logger.info("Added project-specific agent rules to planning prompt")

            # プロジェクトファイル一覧を読み込み
            file_list_context = self._load_file_list_context()
            if file_list_context:
                planning_prompt = planning_prompt + "\n" + file_list_context
                self.logger.info("Added project file list to planning prompt")

            # Send system prompt to LLM client
            if hasattr(self.llm_client, "send_system_prompt"):
                self.llm_client.send_system_prompt(planning_prompt)
                self.logger.info("Loaded planning system prompt with MCP function definitions")
            else:
                self.logger.warning("LLM client does not support send_system_prompt")

        except Exception as e:
            self.logger.error("Failed to load planning system prompt: %s", str(e))

    def _post_phase_comment(self, phase: str, status: str, details: str = "") -> None:
        """Post a comment about the current phase status to Issue/MR.
        
        Args:
            phase: The phase name (e.g., "planning", "execution", "reflection", "pre_planning", "verification")
            status: The status (e.g., "started", "completed", "failed")
            details: Additional details to include in the comment
        """
        try:
            # Build comment based on phase and status
            emoji_map = {
                "pre_planning": "🔍",
                "planning": "🎯",
                "execution": "⚙️",
                "reflection": "🔍",
                "revision": "📝",
                "verification": "🔍",
            }

            status_emoji_map = {
                "started": "▶️",
                "completed": "✅",
                "failed": "❌",
                "in_progress": "🔄",
            }

            phase_emoji = emoji_map.get(phase, "📌")
            status_emoji = status_emoji_map.get(status, "ℹ️")

            # Build comment title
            phase_title = phase.replace("_", " ").title()
            status_title = status.replace("_", " ").title()

            comment_lines = [
                f"## {phase_emoji} {phase_title} Phase - {status_emoji} {status_title}",
                "",
            ]

            # Add details if provided
            if details:
                comment_lines.append(details)
                comment_lines.append("")

            # Add timestamp
            timestamp = datetime.now().strftime(DATETIME_FORMAT)
            comment_lines.append(f"*{timestamp}*")

            comment_content = "\n".join(comment_lines)

            # Post comment to Issue/MR using Task.comment method
            if hasattr(self.task, "comment"):
                self.task.comment(comment_content)
                self.logger.info(f"Posted {phase} phase {status} comment to Issue/MR")
            else:
                self.logger.warning("Task does not support comment, cannot post phase comment")

        except Exception as e:
            self.logger.error("Failed to post phase comment: %s", str(e))

    def _post_llm_call_comment(
        self,
        phase: str,
        llm_response: dict[str, Any] | str | None = None,
        task_id: str | None = None,
    ) -> None:
        """LLM呼び出し完了時にコメントをIssue/MRに投稿する.

        仕様書に従い、以下のルールでコメント内容を決定:
        1. LLM応答にcommentフィールドがある場合: その内容を使用（常に優先）
        2. commentフィールドがない場合: フェーズ名+LLM呼び出し回数のデフォルトメッセージ

        Args:
            phase: 現在のフェーズ名
            llm_response: LLM応答（dictまたはstr）
            task_id: 実行中のアクションID（executionフェーズ用）

        """
        # LLM呼び出しコメント機能が無効の場合は何もしない
        if not self.llm_call_comments_enabled:
            return

        try:
            # LLM呼び出し回数をインクリメント
            self.llm_call_count += 1

            # フェーズ名の日本語表示用マッピング
            phase_names: dict[str, str] = {
                "pre_planning": "計画前情報収集",
                "planning": "計画作成",
                "execution": "アクション実行",
                "reflection": "リフレクション",
                "revision": "計画修正",
                "verification": "検証",
                "replan_decision": "再計画判断",
            }

            phase_display_name = phase_names.get(phase, phase.replace("_", " ").title())

            # LLM応答からcommentフィールドを取得
            comment_content: str | None = None
            if isinstance(llm_response, dict):
                comment_content = llm_response.get("comment")
            elif isinstance(llm_response, str):
                # JSON文字列の場合、パースしてcommentフィールドを探す
                try:
                    parsed = json.loads(llm_response)
                    if isinstance(parsed, dict):
                        comment_content = parsed.get("comment")
                except (json.JSONDecodeError, ValueError):
                    pass

            # コメント内容の決定
            if comment_content:
                # commentフィールドがある場合: その内容を使用
                comment_lines = [
                    f"## ✅ {phase_display_name} - LLM呼び出し #{self.llm_call_count}",
                    "",
                    comment_content,
                    "",
                ]
            else:
                # commentフィールドがない場合: デフォルトメッセージ
                default_message = self.phase_default_messages.get(
                    phase, "処理が完了しました",
                )
                # executionフェーズの場合はtask_idを含める
                if phase == "execution" and task_id:
                    default_message = f"アクション「{task_id}」の実行が完了しました"

                comment_lines = [
                    f"## ✅ {phase_display_name} - LLM呼び出し #{self.llm_call_count} 完了",
                    "",
                    default_message,
                    "",
                ]

            # タイムスタンプを追加
            timestamp = datetime.now().strftime(DATETIME_FORMAT)
            comment_lines.append(f"*{timestamp}*")

            comment_text = "\n".join(comment_lines)

            # Issue/MRにコメント投稿
            if hasattr(self.task, "comment"):
                self.task.comment(comment_text)
                self.logger.info(
                    "LLM呼び出しコメントを投稿: phase=%s, call_count=%d",
                    phase,
                    self.llm_call_count,
                )
            else:
                self.logger.warning("タスクがcommentをサポートしていません")

        except Exception as e:
            # コメント投稿失敗はメイン処理に影響させない
            self.logger.warning("LLM呼び出しコメントの投稿に失敗: %s", e)

    def _post_tool_call_before_comment(
        self,
        tool_name: str,
        arguments: dict[str, Any] | str,
    ) -> None:
        """ツール呼び出し前にコメントをIssue/MRに投稿する.

        仕様書に従い、以下の形式でコメント:
        ## 🔧 ツール呼び出し - {ツール名}
        **引数**: {引数（40文字を超える場合は切り捨て）}
        *{タイムスタンプ}*

        Args:
            tool_name: 呼び出すツール名
            arguments: ツール引数（dictまたはJSON文字列）

        """
        # LLM呼び出しコメント機能が無効の場合は何もしない
        if not self.llm_call_comments_enabled:
            return

        try:
            # 引数をJSON文字列に変換
            if isinstance(arguments, dict):
                args_str = json.dumps(arguments, ensure_ascii=False)
            else:
                args_str = str(arguments)

            # 最大文字数を超える場合は切り捨て
            if len(args_str) > TOOL_ARGS_MAX_LENGTH:
                args_str = args_str[:TOOL_ARGS_MAX_LENGTH] + "..."

            # コメント構築
            timestamp = datetime.now().strftime(DATETIME_FORMAT)
            comment_lines = [
                f"## 🔧 ツール呼び出し - {tool_name}",
                "",
                f"**引数**: {args_str}",
                "",
                f"*{timestamp}*",
            ]

            comment_text = "\n".join(comment_lines)

            # Issue/MRにコメント投稿
            if hasattr(self.task, "comment"):
                self.task.comment(comment_text)
                self.logger.info("ツール呼び出し前コメントを投稿: %s", tool_name)
            else:
                self.logger.warning("タスクがcommentをサポートしていません")

        except Exception as e:
            # コメント投稿失敗はメイン処理に影響させない
            self.logger.warning("ツール呼び出し前コメントの投稿に失敗: %s", e)

    def _post_tool_call_after_comment(
        self,
        tool_name: str,
        success: bool,
    ) -> None:
        """ツール呼び出し後にコメントをIssue/MRに投稿する.

        仕様書に従い、以下の形式でコメント:
        成功時: ## ✅ ツール完了 - {ツール名}
        失敗時: ## ❌ ツール失敗 - {ツール名}

        Args:
            tool_name: 呼び出したツール名
            success: 成功したかどうか

        """
        # LLM呼び出しコメント機能が無効の場合は何もしない
        if not self.llm_call_comments_enabled:
            return

        try:
            timestamp = datetime.now().strftime(DATETIME_FORMAT)

            if success:
                comment_lines = [
                    f"## ✅ ツール完了 - {tool_name}",
                    "",
                    "結果: 成功",
                    "",
                    f"*{timestamp}*",
                ]
            else:
                comment_lines = [
                    f"## ❌ ツール失敗 - {tool_name}",
                    "",
                    "結果: 失敗",
                    "",
                    f"*{timestamp}*",
                ]

            comment_text = "\n".join(comment_lines)

            # Issue/MRにコメント投稿
            if hasattr(self.task, "comment"):
                self.task.comment(comment_text)
                self.logger.info(
                    "ツール呼び出し後コメントを投稿: %s, success=%s", tool_name, success,
                )
            else:
                self.logger.warning("タスクがcommentをサポートしていません")

        except Exception as e:
            # コメント投稿失敗はメイン処理に影響させない
            self.logger.warning("ツール呼び出し後コメントの投稿に失敗: %s", e)

    def _post_llm_error_comment(
        self,
        phase: str,
        error_message: str,
    ) -> None:
        """LLM呼び出しエラー時にコメントをIssue/MRに投稿する.

        仕様書に従い、以下の形式でコメント:
        ## ⚠️ LLM呼び出しエラー - {フェーズ名}
        **エラー内容**: {エラーメッセージ}
        リトライを試みます...
        *{タイムスタンプ}*

        Args:
            phase: 現在のフェーズ名
            error_message: エラーメッセージ

        """
        # LLM呼び出しコメント機能が無効の場合は何もしない
        if not self.llm_call_comments_enabled:
            return

        try:
            # フェーズ名の日本語表示用マッピング
            phase_names: dict[str, str] = {
                "pre_planning": "計画前情報収集",
                "planning": "計画作成",
                "execution": "アクション実行",
                "reflection": "リフレクション",
                "revision": "計画修正",
                "verification": "検証",
                "replan_decision": "再計画判断",
            }

            phase_display_name = phase_names.get(phase, phase.replace("_", " ").title())
            timestamp = datetime.now().strftime(DATETIME_FORMAT)

            comment_lines = [
                f"## ⚠️ LLM呼び出しエラー - {phase_display_name}",
                "",
                f"**エラー内容**: {error_message}",
                "",
                "リトライを試みます...",
                "",
                f"*{timestamp}*",
            ]

            comment_text = "\n".join(comment_lines)

            # Issue/MRにコメント投稿
            if hasattr(self.task, "comment"):
                self.task.comment(comment_text)
                self.logger.info("LLMエラーコメントを投稿: phase=%s", phase)
            else:
                self.logger.warning("タスクがcommentをサポートしていません")

        except Exception as e:
            # コメント投稿失敗はメイン処理に影響させない
            self.logger.warning("LLMエラーコメントの投稿に失敗: %s", e)

    def _post_tool_error_comment(
        self,
        tool_name: str,
        error_message: str,
        task_id: str | None = None,
    ) -> None:
        """ツール実行エラー時にコメントをIssue/MRに投稿する.

        仕様書に従い、以下の形式でコメント:
        ## ❌ エラー発生 - {ツール名}
        **エラー内容**: {エラーメッセージ}
        **発生したアクション**: {task_id}
        *{タイムスタンプ}*

        Args:
            tool_name: ツール名
            error_message: エラーメッセージ
            task_id: 発生したアクションのID（オプション）

        """
        # LLM呼び出しコメント機能が無効の場合は何もしない
        if not self.llm_call_comments_enabled:
            return

        try:
            timestamp = datetime.now().strftime(DATETIME_FORMAT)

            comment_lines = [
                f"## ❌ エラー発生 - {tool_name}",
                "",
                f"**エラー内容**: {error_message}",
            ]

            if task_id:
                comment_lines.append("")
                comment_lines.append(f"**発生したアクション**: {task_id}")

            comment_lines.extend([
                "",
                f"*{timestamp}*",
            ])

            comment_text = "\n".join(comment_lines)

            # Issue/MRにコメント投稿
            if hasattr(self.task, "comment"):
                self.task.comment(comment_text)
                self.logger.info(
                    "ツールエラーコメントを投稿: tool=%s, task_id=%s",
                    tool_name,
                    task_id,
                )
            else:
                self.logger.warning("タスクがcommentをサポートしていません")

        except Exception as e:
            # コメント投稿失敗はメイン処理に影響させない
            self.logger.warning("ツールエラーコメントの投稿に失敗: %s", e)

    def restore_planning_state(self, planning_state: dict[str, Any]) -> None:
        """Restore planning state from paused task.
        
        Args:
            planning_state: Planning state dictionary from task_state.json
        """
        if not planning_state or not planning_state.get("enabled"):
            return

        # Restore planning state
        self.current_phase = planning_state.get("current_phase", "planning")
        self.action_counter = planning_state.get("action_counter", 0)
        self.revision_counter = planning_state.get("revision_counter", 0)

        # LLM呼び出し回数を復元
        self.llm_call_count = planning_state.get("llm_call_count", 0)

        # Restore checklist comment ID if available
        saved_checklist_id = planning_state.get("checklist_comment_id")
        if saved_checklist_id is not None:
            self.checklist_comment_id = saved_checklist_id
            self.plan_comment_id = saved_checklist_id

        # Restore pre-planning result if available
        saved_pre_planning_result = planning_state.get("pre_planning_result")
        if saved_pre_planning_result is not None:
            self.pre_planning_result = saved_pre_planning_result

        # Restore selected environment if available
        saved_selected_environment = planning_state.get("selected_environment")
        if saved_selected_environment is not None:
            self.selected_environment = saved_selected_environment

        # Restore pre-planning manager state if available
        saved_pre_planning_state = planning_state.get("pre_planning_state")
        if saved_pre_planning_state and self.pre_planning_manager:
            self.pre_planning_manager.restore_pre_planning_state(saved_pre_planning_state)

        self.logger.info(
            "Planning状態を復元しました: phase=%s, action_counter=%d, revision_counter=%d, "
            "llm_call_count=%d, checklist_id=%s, selected_environment=%s",
            self.current_phase,
            self.action_counter,
            self.revision_counter,
            self.llm_call_count,
            self.checklist_comment_id,
            self.selected_environment,
        )

        # Load existing plan from history
        if self.history_store.has_plan():
            plan_entry = self.history_store.get_latest_plan()
            if plan_entry:
                self.current_plan = plan_entry.get("plan") or plan_entry.get("updated_plan")
                self.logger.info("既存のプランを復元しました")

    def get_planning_state(self) -> dict[str, Any]:
        """Get current planning state for pause.
        
        Returns:
            Planning state dictionary
        """
        # Get total actions count for stop message
        total_actions = 0
        if self.current_plan:
            action_plan = self.current_plan.get("action_plan", {})
            total_actions = len(action_plan.get("actions", []))

        state = {
            "enabled": True,
            "current_phase": self.current_phase,
            "action_counter": self.action_counter,
            "revision_counter": self.revision_counter,
            "llm_call_count": self.llm_call_count,
            "checklist_comment_id": self.plan_comment_id,
            "total_actions": total_actions,
            "pre_planning_result": self.pre_planning_result,
            "selected_environment": self.selected_environment,
        }

        # Add pre-planning manager state if available
        if self.pre_planning_manager:
            state["pre_planning_state"] = self.pre_planning_manager.get_pre_planning_state()

        return state

    def _check_pause_signal(self) -> bool:
        """Check if pause signal is detected.
        
        Returns:
            True if pause signal is detected, False otherwise
        """
        if self.pause_manager is None:
            return False

        return self.pause_manager.check_pause_signal()

    def _check_stop_signal(self) -> bool:
        """Check if stop signal (assignee removal) is detected.
        
        Returns:
            True if stop signal is detected, False otherwise
        """
        if self.stop_manager is None:
            return False

        # Check if it's time to check and if bot is unassigned
        if self.stop_manager.should_check_now():
            return not self.stop_manager.check_assignee_status(self.task)

        return False

    def _handle_stop(self) -> None:
        """Handle stop operation for planning mode."""
        if self.stop_manager is None:
            self.logger.warning("Stop manager not set, cannot stop")
            return

        # Get current planning state with total actions
        planning_state = self.get_planning_state()

        # 最終要約を作成してコンテキストをcompletedに移動
        self.context_manager.stop()

        # コメントとラベル更新
        self.stop_manager.post_stop_notification(
            self.task,
            planning_state=planning_state,
        )

    def _check_and_add_new_comments(self) -> None:
        """新規コメントを検出してコンテキストに追加する.
        
        comment_detection_managerがNoneの場合は何もしません。
        """
        if self.comment_detection_manager is None:
            return

        try:
            new_comments = self.comment_detection_manager.check_for_new_comments()
            if new_comments:
                self.comment_detection_manager.add_to_context(
                    self.llm_client, new_comments,
                )
                self.logger.info(
                    "新規コメント %d件をコンテキストに追加しました", len(new_comments),
                )
        except Exception as e:
            self.logger.warning("新規コメントの検出中にエラー発生: %s", e)

    def _load_project_agent_rules(self) -> str:
        """プロジェクト固有のエージェントルールを読み込む.

        Returns:
            プロジェクト固有のエージェントルール文字列

        """
        import os

        from handlers.project_agent_rules_loader import ProjectAgentRulesLoader

        # 環境変数による有効/無効チェック
        env_enabled = os.getenv("PROJECT_AGENT_RULES_ENABLED")
        if env_enabled is not None:
            if env_enabled.lower() in ("false", "0", "no"):
                return ""
        else:
            # 環境変数が設定されていない場合は設定ファイルをチェック
            rules_config = self.config.get("project_agent_rules", {})
            if not rules_config.get("enabled", True):
                return ""

        # タスクからowner/repo (GitHub) または project_id (GitLab) を取得してMCPモードで読み込み
        try:
            task_key = self.task.get_task_key()
            owner = getattr(task_key, "owner", None)
            repo = getattr(task_key, "repo", None)
            project_id = getattr(task_key, "project_id", None)

            # GitHub の場合
            if owner and repo and "github" in self.mcp_clients:
                loader = ProjectAgentRulesLoader(
                    config=self.config,
                    mcp_client=self.mcp_clients["github"],
                    owner=owner,
                    repo=repo,
                )
                return loader.load_rules()

            # GitLab の場合
            if project_id and "gitlab" in self.mcp_clients:
                loader = ProjectAgentRulesLoader(
                    config=self.config,
                    mcp_client=self.mcp_clients["gitlab"],
                    project_id=str(project_id),
                )
                return loader.load_rules()
        except Exception as e:
            self.logger.warning("プロジェクトルールの読み込みに失敗しました: %s", e)

        return ""

    def _load_file_list_context(self) -> str:
        """プロジェクトファイル一覧を読み込む.

        Returns:
            プロジェクトファイル一覧文字列

        """
        from handlers.file_list_context_loader import FileListContextLoader

        try:
            loader = FileListContextLoader(
                config=self.config,
                mcp_clients=self.mcp_clients,
            )
            return loader.load_file_list(self.task)
        except Exception as e:
            self.logger.warning("ファイル一覧の読み込みに失敗しました: %s", e)
            return ""

