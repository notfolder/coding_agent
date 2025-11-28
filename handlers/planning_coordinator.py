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

        # Set issue_id for cross-task history tracking
        if hasattr(task, "number"):
            self.history_store.issue_id = str(task.number)

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
            
            # Post start comment
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
                        "execution", "failed", f"Action failed: {error_msg}"
                    )

                    # 再計画判断をLLMに依頼
                    if self.replan_manager.enabled:
                        decision = self._request_execution_replan_decision(
                            current_action, result
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


    def _execute_planning_phase(self) -> dict[str, Any] | None:
        """Execute the planning phase.
        
        Returns:
            Planning result dictionary or None if planning failed
        """
        try:
            # Get past executions for context
            issue_id = getattr(self.task, 'number', None)
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
            
            return plan
            
        except Exception:
            self.logger.exception("Planning phase execution failed")
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
                    if self._execute_function_call(function, error_state):
                        # Critical error occurred
                        return {
                            "status": "error",
                            "error": "Too many consecutive tool errors",
                            "action": current_action,
                        }
            
            # Try to parse JSON response
            try:
                data = json.loads(resp) if isinstance(resp, str) else resp
                
                # Post comment to Issue/MR if provided
                if isinstance(data, dict) and data.get("comment"):
                    self.task.comment(data["comment"])
                    self.logger.info("Posted comment to Issue/MR from action response")
                
                # Check if done
                if data.get("done"):
                    return {"done": True, "status": "completed", "result": data}
                
                return {"status": "success", "result": data, "action": current_action}
            except (json.JSONDecodeError, ValueError):
                # If not JSON, treat as text response
                return {"status": "success", "result": resp, "action": current_action}
            
        except Exception as e:
            self.logger.exception("Action execution failed: %s", e)
            return {"status": "error", "error": str(e)}

    def _execute_function_call(self, function: dict[str, Any], error_state: dict[str, Any]) -> bool:
        """Execute a single function call.
        
        Args:
            function: Function call information (dict or object with name/arguments)
            error_state: Error state tracking dictionary
            
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
                    
                    return False
                    
                except Exception as e:
                    error_msg = str(e)
                    self.logger.exception("Command execution failed: %s", error_msg)
                    
                    # Post error to task
                    self.task.comment(f"コマンド実行エラー ({name}): {error_msg}")
                    
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
                            f"同じツール({name})で{MAX_CONSECUTIVE_TOOL_ERRORS}回連続エラーが発生したため処理を中止します。"
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
                
                # Post error to task
                self.task.comment(f"ツール実行エラー ({name}): {error_msg}")
                
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
                        f"同じツール({name})で{MAX_CONSECUTIVE_TOOL_ERRORS}回連続エラーが発生したため処理を中止します。"
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
            
            # Save reflection
            if reflection:
                self.history_store.save_reflection(reflection)
            
            return reflection
            
        except Exception as e:
            self.logger.exception(f"Reflection phase failed: {e}")
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

            # Save revision
            if revised_plan:
                self.history_store.save_revision(revised_plan, reflection)

            return revised_plan

        except Exception:
            self.logger.exception("Plan revision failed")
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
                "actions", []
            )[: self.action_counter]

            # LLMに残りのアクションの再生成を依頼
            remaining_prompt = self._build_partial_replan_prompt(
                completed_actions, decision
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
                "actions", []
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
            f"at {datetime.now().strftime(DATETIME_FORMAT)}*"
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
            "IMPORTANT - Task Complexity Assessment:",
            "Before creating your plan, evaluate the task complexity:",
            "- Simple (1-2 tool calls): Single file creation/modification, basic operations → Use 1-3 subtasks",
            "- Medium (3-6 tool calls): Multiple related changes, small features → Use 3-6 subtasks",
            "- Complex (7+ tool calls): Major features, large refactoring → Use 6-10 subtasks maximum",
            "",
            "Default to SIMPLER plans. Most tasks are simpler than they appear.",
            "Combine related operations. Don't over-decompose simple tasks.",
        ]
        
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
            '  "action_plan": {...}',
            "}",
        ])
        
        return "\n".join(prompt_parts)

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
            phase: The phase name (e.g., "planning", "execution", "reflection")
            status: The status (e.g., "started", "completed", "failed")
            details: Additional details to include in the comment
        """
        try:
            # Build comment based on phase and status
            emoji_map = {
                "planning": "🎯",
                "execution": "⚙️",
                "reflection": "🔍",
                "revision": "📝",
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
        
        # Restore checklist comment ID if available
        saved_checklist_id = planning_state.get("checklist_comment_id")
        if saved_checklist_id is not None:
            self.checklist_comment_id = saved_checklist_id
            self.plan_comment_id = saved_checklist_id
        
        self.logger.info(
            "Planning状態を復元しました: phase=%s, action_counter=%d, revision_counter=%d, checklist_id=%s",
            self.current_phase,
            self.action_counter,
            self.revision_counter,
            self.checklist_comment_id,
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
        
        return {
            "enabled": True,
            "current_phase": self.current_phase,
            "action_counter": self.action_counter,
            "revision_counter": self.revision_counter,
            "checklist_comment_id": self.plan_comment_id,
            "total_actions": total_actions,
        }

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
        
        # Stop the task with planning state
        self.stop_manager.stop_task(
            self.task,
            self.task.uuid,
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
                    self.llm_client, new_comments
                )
                self.logger.info(
                    "新規コメント %d件をコンテキストに追加しました", len(new_comments)
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

