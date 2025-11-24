"""Planning coordinator module.

This module provides the main coordination logic for planning-based task execution.
"""
from __future__ import annotations

import json
import logging
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
            llm_client: LLM client instance
            mcp_clients: Dictionary of MCP tool clients
            task: Task object to process
        """
        self.config = config
        self.llm_client = llm_client
        self.mcp_clients = mcp_clients
        self.task = task
        self.logger = logging.getLogger(__name__)
        
        # Initialize history store
        self.history_store = PlanningHistoryStore(task.uuid, config)
        
        # Current state
        self.current_phase = "planning"
        self.current_plan = None
        self.action_counter = 0
        self.revision_counter = 0

    def execute_with_planning(self) -> bool:
        """Execute task with planning capabilities.
        
        Main execution loop that handles planning, execution, reflection, and revision.
        
        Returns:
            True if task completed successfully, False otherwise
        """
        try:
            # Step 1: Check for existing plan
            if self.history_store.has_plan():
                self.logger.info("Found existing plan, loading...")
                plan_entry = self.history_store.get_latest_plan()
                if plan_entry:
                    self.current_plan = plan_entry.get("plan") or plan_entry.get("updated_plan")
                    self.current_phase = "execution"
            else:
                # Step 2: Execute planning phase
                self.logger.info("No existing plan, executing planning phase...")
                self.current_plan = self._execute_planning_phase()
                if self.current_plan:
                    self.history_store.save_plan(self.current_plan)
                    self.current_phase = "execution"
                else:
                    self.logger.error("Planning phase failed")
                    return False

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
                
                # Check if reflection is needed
                if self._should_reflect(result):
                    reflection = self._execute_reflection_phase(result)
                    
                    if reflection and reflection.get("plan_revision_needed"):
                        # Revise plan if needed
                        revised_plan = self._revise_plan(reflection)
                        if revised_plan:
                            self.current_plan = revised_plan
                
                # Check for completion
                if result.get("done"):
                    self.logger.info("Task completed successfully")
                    break
            
            return True
            
        except Exception as e:
            self.logger.exception(f"Planning execution failed: {e}")
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
            response = self.llm_client.process(planning_prompt)
            
            # Parse response
            plan = self._parse_planning_response(response)
            
            return plan
            
        except Exception as e:
            self.logger.exception(f"Planning phase execution failed: {e}")
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
            result = self.llm_client.process(action_prompt)
            
            return {"status": "success", "result": result, "action": current_action}
            
        except Exception as e:
            self.logger.exception(f"Action execution failed: {e}")
            return {"status": "error", "error": str(e)}

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
        if interval > 0 and self.action_counter % interval == 0:
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
            response = self.llm_client.process(reflection_prompt)
            
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
            self.revision_counter += 1
            
            if self.revision_counter > max_revisions:
                self.logger.error("Maximum plan revisions exceeded")
                return None
            
            # Build revision prompt
            revision_prompt = self._build_revision_prompt(reflection)
            
            # Get revised plan from LLM
            response = self.llm_client.process(revision_prompt)
            
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
        return f"Execute the following action:\n{json.dumps(action, indent=2)}"

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
            
            # Try to parse as JSON
            return json.loads(response)
        except json.JSONDecodeError:
            self.logger.warning("Failed to parse planning response as JSON")
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
            
            return json.loads(response)
        except json.JSONDecodeError:
            self.logger.warning("Failed to parse reflection response as JSON")
            return None
