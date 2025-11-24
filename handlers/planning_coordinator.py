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

from handlers.planning_history_store import PlanningHistoryStore

if TYPE_CHECKING:
    from handlers.task import Task


class PlanningCoordinator:
    """Coordinates planning-based task execution.
    
    Manages the planning process including goal understanding, task decomposition,
    action execution, reflection, and plan revision.
    """

    def __init__(
        self,
        config: dict[str, Any],
        llm_client: object,
        mcp_clients: dict[str, object],
        task: Task,
    ) -> None:
        """Initialize the planning coordinator.
        
        Args:
            config: Planning configuration
            llm_client: LLM client instance (used as template for creating planning client)
            mcp_clients: Dictionary of MCP tool clients
            task: Task object to process
        """
        self.config = config
        self.mcp_clients = mcp_clients
        self.task = task
        self.logger = logging.getLogger(__name__)
        
        # Initialize history store
        self.history_store = PlanningHistoryStore(task.uuid, config)
        
        # Set issue_id for cross-task history tracking
        if hasattr(task, "number"):
            self.history_store.issue_id = str(task.number)
        
        # Create planning-specific LLM client with message store and context dir
        from clients.lm_client import get_llm_client
        from context_storage.message_store import MessageStore
        
        # Use task context directory for planning
        context_dir = Path("contexts") / "running" / task.uuid
        context_dir.mkdir(parents=True, exist_ok=True)
        
        # Get the main config for LLM client initialization
        main_config = config.get("main_config", {})
        
        message_store = MessageStore(context_dir, main_config)
        
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
            context_dir=context_dir,
        )
        
        # Load and send planning-specific system prompt
        self._load_planning_system_prompt()
        
        # Send initial task information to LLM
        self._send_initial_task_prompt()
        
        # Current state
        self.current_phase = "planning"
        self.current_plan = None
        self.action_counter = 0
        self.revision_counter = 0
        
        # Checkbox tracking for progress updates
        self.plan_comment_id = None  # ID of the comment containing the checklist

    def execute_with_planning(self) -> bool:
        """Execute task with planning capabilities.
        
        Main execution loop that handles planning, execution, reflection, and revision.
        
        Returns:
            True if task completed successfully, False otherwise
        """
        try:
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

            # Post execution start
            self._post_phase_comment("execution", "started", "Beginning execution of planned actions...")

            # Step 3: Execution loop
            max_iterations = self.config.get("max_subtasks", 100)
            iteration = 0
            
            while iteration < max_iterations and not self._is_complete():
                iteration += 1
                
                # Execute next action
                result = self._execute_action()
                
                if result is None:
                    self.logger.warning("No more actions to execute")
                    break
                
                # Check for action failure
                if result.get("status") == "error":
                    error_msg = result.get("error", "Unknown error occurred")
                    self._post_phase_comment("execution", "failed", f"Action failed: {error_msg}")
                    # Continue or stop based on configuration
                    if not self.config.get("continue_on_error", False):
                        return False
                
                # Update progress checklist
                self._update_checklist_progress(self.action_counter - 1)
                
                # Check if reflection is needed
                if self._should_reflect(result):
                    self._post_phase_comment("reflection", "started", f"Analyzing results after {self.action_counter} actions...")
                    reflection = self._execute_reflection_phase(result)
                    
                    if reflection and reflection.get("plan_revision_needed"):
                        # Revise plan if needed
                        self._post_phase_comment("revision", "started", "Plan revision needed based on reflection.")
                        revised_plan = self._revise_plan(reflection)
                        if revised_plan:
                            self.current_plan = revised_plan
                            self._post_phase_comment("revision", "completed", "Plan has been revised and updated.")
                        else:
                            self._post_phase_comment("revision", "failed", "Could not revise plan.")
                    else:
                        self._post_phase_comment("reflection", "completed", "Reflection complete, continuing with current plan.")
                
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
            response, _ = self.llm_client.get_response()  # Unpack tuple, ignore functions
            
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
            resp, functions = self.llm_client.get_response()
            self.logger.info("Action execution LLM response: %s", resp)
            
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
            
            # Execute the tool
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
            response, _ = self.llm_client.get_response()  # Unpack tuple, ignore functions
            
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
            response, _ = self.llm_client.get_response()  # Unpack tuple, ignore functions
            
            # Parse revised plan
            revised_plan = self._parse_planning_response(response)
            
            # Save revision
            if revised_plan:
                self.history_store.save_revision(revised_plan, reflection)
            
            return revised_plan
            
        except Exception as e:
            self.logger.exception(f"Plan revision failed: {e}")
            return None

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
        prompt_parts = [
            "Create a comprehensive plan for the following task:",
            "",
            f"Task: {self.task.title}",
            f"Description: {self.task.body}",
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
            
            # Post to Issue/MR using task's comment method
            if hasattr(self.task, "comment"):
                self.task.comment(checklist_content)
                self.logger.info("Posted execution plan checklist to Issue/MR")
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
            
            # Update the comment if task supports it (not implemented yet)
            # For now, just add a new comment with progress update
            if hasattr(self.task, "comment"):
                self.task.comment(checklist_content)
            
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
            
            # Update or add comment using Task.comment method
            if hasattr(self.task, "comment"):
                self.task.comment(checklist_content)
            
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
            
            # Send system prompt to LLM client
            if hasattr(self.llm_client, "send_system_prompt"):
                self.llm_client.send_system_prompt(planning_prompt)
                self.logger.info("Loaded planning system prompt")
            else:
                self.logger.warning("LLM client does not support send_system_prompt")
                
        except Exception as e:
            self.logger.error("Failed to load planning system prompt: %s", str(e))

    def _send_initial_task_prompt(self) -> None:
        """Send initial task information (issue/MR details) to LLM client."""
        try:
            # Get task prompt with issue/MR information
            task_prompt = self.task.get_prompt()
            
            # Send task information to LLM
            if hasattr(self.llm_client, "send_user_message"):
                self.llm_client.send_user_message(task_prompt)
                self.logger.info("Sent initial task information to LLM")
            else:
                self.logger.warning("LLM client does not support send_user_message")
                
        except Exception as e:
            self.logger.error("Failed to send initial task prompt: %s", str(e))

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
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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
