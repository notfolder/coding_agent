"""再計画判断プロンプト生成モジュール.

各フェーズ用の再計画判断プロンプトを生成するクラスを定義します。
"""
from __future__ import annotations

import json
from typing import Any


class ReplanPromptBuilder:
    """各フェーズ用の再計画判断プロンプトを生成するクラス.

    仕様書で定義されたプロンプトテンプレートを使用して、
    LLMへの再計画判断依頼プロンプトを生成します。
    """

    # 再計画判断のJSON応答フォーマット
    REPLAN_DECISION_FORMAT = """{
  "replan_decision": {
    "replan_needed": true,
    "confidence": 0.85,
    "reasoning": "Explanation of the decision",
    "replan_type": "partial_replan",
    "target_phase": "task_decomposition",
    "replan_level": 2,
    "issues_found": [
      "Issue 1",
      "Issue 2"
    ],
    "recommended_actions": [
      "Action 1",
      "Action 2"
    ],
    "clarification_needed": false,
    "clarification_questions": []
  }
}"""

    def __init__(self, available_tools: list[str] | None = None) -> None:
        """プロンプトビルダーを初期化する.

        Args:
            available_tools: 利用可能なツールのリスト

        """
        self.available_tools = available_tools or []

    def build_goal_understanding_prompt(
        self,
        goal_understanding_result: dict[str, Any],
        task_request: str,
        context_info: str = "",
    ) -> str:
        """目標の理解フェーズ用の再計画判断プロンプトを生成する.

        Args:
            goal_understanding_result: 目標理解の結果
            task_request: 元のタスク要求
            context_info: コンテキスト情報

        Returns:
            プロンプト文字列

        """
        return f"""You have completed the goal understanding phase.
Now evaluate whether the understanding is sufficient to proceed.

**Current Goal Understanding:**
{json.dumps(goal_understanding_result, indent=2, ensure_ascii=False)}

**Original Task Request:**
{task_request}

**Available Context:**
{context_info}

**Evaluation Criteria:**
1. Is the main objective clearly defined?
2. Are all success criteria identifiable?
3. Are there any ambiguities or contradictions in the requirements?
4. Is there sufficient context to proceed with task decomposition?
5. Are there any questions that need clarification from the user?

Based on your evaluation, provide a replan decision in the following JSON format:
{self.REPLAN_DECISION_FORMAT}

Consider carefully whether replanning is truly necessary. Only recommend replanning if:
- Critical information is missing that would prevent successful task completion
- There are significant ambiguities that could lead to incorrect implementation
- User clarification is essential before proceeding

If clarification is needed, set clarification_needed to true and provide clarification_questions.
If you decide to proceed with assumptions, set replan_needed to false
and list the assumptions in assumptions_to_make field."""

    def build_task_decomposition_prompt(
        self,
        task_decomposition_result: dict[str, Any],
        goal_understanding: dict[str, Any],
    ) -> str:
        """タスクの分解フェーズ用の再計画判断プロンプトを生成する.

        Args:
            task_decomposition_result: タスク分解の結果
            goal_understanding: 目標理解の結果

        Returns:
            プロンプト文字列

        """
        tools_str = (
            "\n".join(f"- {tool}" for tool in self.available_tools)
            if self.available_tools
            else "Not specified"
        )

        return f"""You have completed the task decomposition phase.
Now evaluate whether the decomposition is appropriate and executable.

**Task Decomposition Result:**
{json.dumps(task_decomposition_result, indent=2, ensure_ascii=False)}

**Original Goal:**
{json.dumps(goal_understanding, indent=2, ensure_ascii=False)}

**Available Tools:**
{tools_str}

**Evaluation Criteria:**
1. Are all subtasks clearly defined and actionable?
2. Are the dependencies between subtasks correctly identified?
3. Is the complexity estimation reasonable?
4. Are the required tools available for each subtask?
5. Is the decomposition granularity appropriate (not too fine or too coarse)?
6. Are there any missing steps that should be included?

Based on your evaluation, provide a replan decision in the following JSON format:
{self.REPLAN_DECISION_FORMAT}

For task decomposition issues, use replan_type: "task_redecomposition"

Consider carefully whether replanning is truly necessary. Only recommend replanning if:
- Subtasks are not executable with available tools
- Critical steps are missing
- The decomposition has fundamental issues that would cause execution failures"""

    def build_action_sequence_prompt(
        self,
        action_plan: dict[str, Any],
        subtasks: list[dict[str, Any]],
        tool_availability: dict[str, bool] | None = None,
    ) -> str:
        """行動系列の生成フェーズ用の再計画判断プロンプトを生成する.

        Args:
            action_plan: アクション計画
            subtasks: サブタスクのリスト
            tool_availability: ツールの利用可能性

        Returns:
            プロンプト文字列

        """
        tool_status_str = ""
        if tool_availability:
            for tool, available in tool_availability.items():
                status = "Available" if available else "Unavailable"
                tool_status_str += f"- {tool}: {status}\n"
        else:
            tool_status_str = "All tools assumed available"

        return f"""You have completed the action sequence generation phase. Now evaluate whether the plan is executable.

**Action Plan:**
{json.dumps(action_plan, indent=2, ensure_ascii=False)}

**Subtasks:**
{json.dumps(subtasks, indent=2, ensure_ascii=False)}

**Available Tools and Their Status:**
{tool_status_str}

**Evaluation Criteria:**
1. Can all specified tools be executed with the given parameters?
2. Are the action dependencies correctly ordered?
3. Are fallback strategies defined for potential failures?
4. Are the expected outcomes realistic and verifiable?
5. Is the execution order optimal?

Based on your evaluation, provide a replan decision in the following JSON format:
{self.REPLAN_DECISION_FORMAT}

For action sequence issues, use replan_type: "action_regeneration"

Consider carefully whether replanning is truly necessary. Only recommend replanning if:
- Required tools are unavailable or parameters are invalid
- Action dependencies would cause execution deadlocks
- Critical fallback strategies are missing"""

    def build_execution_prompt(
        self,
        executed_action: dict[str, Any],
        execution_result: dict[str, Any],
        error_info: str = "",
        completed_count: int = 0,
        total_count: int = 0,
        error_count: int = 0,
        consecutive_errors: int = 0,
        remaining_actions: list[dict[str, Any]] | None = None,
    ) -> str:
        """実行フェーズ用の再計画判断プロンプトを生成する.

        Args:
            executed_action: 実行されたアクション
            execution_result: 実行結果
            error_info: エラー情報
            completed_count: 完了したアクション数
            total_count: 総アクション数
            error_count: エラー回数
            consecutive_errors: 連続エラー回数
            remaining_actions: 残りのアクション

        Returns:
            プロンプト文字列

        """
        remaining_str = json.dumps(remaining_actions or [], indent=2, ensure_ascii=False)

        return f"""You have executed an action. Evaluate whether execution can continue or replanning is needed.

**Executed Action:**
{json.dumps(executed_action, indent=2, ensure_ascii=False)}

**Execution Result:**
{json.dumps(execution_result, indent=2, ensure_ascii=False)}

**Error Information (if any):**
{error_info}

**Current Plan Progress:**
- Completed actions: {completed_count}/{total_count}
- Error count: {error_count}
- Consecutive errors: {consecutive_errors}

**Remaining Actions:**
{remaining_str}

**Evaluation Criteria:**
1. Was the action successful? If not, is it recoverable?
2. Are the preconditions for remaining actions still valid?
3. Has the execution context changed in a way that affects the plan?
4. Should execution continue, retry, or replan?

Based on your evaluation, provide a replan decision in the following JSON format:
{self.REPLAN_DECISION_FORMAT}

**Replan Level Guide (for replan_level field):**
- Level 1 (retry): Same action retry - use for transient errors
- Level 2 (partial_replan): Replan from failed action onwards - use for action-specific issues
- Level 3 (action_regeneration): Regenerate entire action plan - use when tools unavailable
- Level 4 (task_redecomposition): Redecompose from subtasks - use when preconditions invalid
- Level 5 (goal_understanding): Start from goal understanding - use when requirements misunderstood

For execution issues, use appropriate replan_type: "retry", "partial_replan", or "full_replan"
Include error_classification: "transient", "persistent", or "fatal"

Consider carefully whether replanning is truly necessary. Prefer:
1. Continue if action succeeded or error is minor
2. Retry if error is transient (network, timeout)
3. Partial replan if only remaining actions need adjustment
4. Full replan only if fundamental assumptions are invalid"""

    def build_reflection_prompt(
        self,
        goal_understanding: dict[str, Any],
        success_criteria: list[str],
        execution_summary: dict[str, Any],
        completed_actions: list[dict[str, Any]],
        current_state: str = "",
    ) -> str:
        """監視と修正フェーズ用の再計画判断プロンプトを生成する.

        Args:
            goal_understanding: 目標理解の結果
            success_criteria: 成功基準のリスト
            execution_summary: 実行サマリー
            completed_actions: 完了したアクションのリスト
            current_state: 現在の状態

        Returns:
            プロンプト文字列

        """
        criteria_str = (
            "\n".join(f"- {c}" for c in success_criteria)
            if success_criteria
            else "Not specified"
        )

        return f"""You have completed the execution of planned actions.
Now evaluate the overall results and determine if any revision is needed.

**Original Goal:**
{json.dumps(goal_understanding, indent=2, ensure_ascii=False)}

**Success Criteria:**
{criteria_str}

**Execution Summary:**
{json.dumps(execution_summary, indent=2, ensure_ascii=False)}

**Actions Completed:**
{json.dumps(completed_actions, indent=2, ensure_ascii=False)}

**Current State:**
{current_state}

**Evaluation Criteria:**
1. Have all success criteria been met?
2. Are there any unintended side effects?
3. Is the implementation quality acceptable?
4. Are there any issues that need to be addressed?
5. Would additional actions improve the outcome?

Based on your evaluation, provide a replan decision in the following JSON format:
{self.REPLAN_DECISION_FORMAT}

For reflection issues, use replan_type: "plan_revision"
Include evaluation_result: "success", "partial_success", or "failure"
Include achievement_rate: 0-100 (percentage of goal achieved)

Consider carefully whether replanning is truly necessary. Only recommend replanning if:
- Critical success criteria are not met
- There are significant quality issues
- Important functionality is missing
- User feedback indicates problems"""
