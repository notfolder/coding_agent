"""Unit tests for ReplanDecision, ReplanPromptBuilder, and ReplanManager."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from handlers.replan_decision import (
    ErrorClassification,
    ReplanDecision,
    ReplanType,
    TargetPhase,
)
from handlers.replan_prompt_builder import ReplanPromptBuilder
from handlers.replan_manager import ReplanManager


class TestReplanDecision(unittest.TestCase):
    """ReplanDecisionデータクラスのテスト."""

    def test_default_values(self) -> None:
        """デフォルト値のテスト."""
        decision = ReplanDecision()
        assert decision.replan_needed is False
        assert decision.confidence == 0.0
        assert decision.reasoning == ""
        assert decision.replan_type == ReplanType.NONE.value
        assert decision.replan_level == 0
        assert decision.issues_found == []

    def test_from_dict_simple(self) -> None:
        """辞書からの生成テスト."""
        data = {
            "replan_needed": True,
            "confidence": 0.85,
            "reasoning": "テスト理由",
            "replan_type": "partial_replan",
            "target_phase": "execution",
            "replan_level": 2,
        }
        decision = ReplanDecision.from_dict(data)
        assert decision.replan_needed is True
        assert decision.confidence == 0.85
        assert decision.reasoning == "テスト理由"
        assert decision.replan_type == "partial_replan"
        assert decision.target_phase == "execution"
        assert decision.replan_level == 2

    def test_from_dict_with_wrapper(self) -> None:
        """replan_decisionラッパー付きの辞書からの生成テスト."""
        data = {
            "replan_decision": {
                "replan_needed": True,
                "confidence": 0.9,
                "reasoning": "ラッパー付きテスト",
            }
        }
        decision = ReplanDecision.from_dict(data)
        assert decision.replan_needed is True
        assert decision.confidence == 0.9
        assert decision.reasoning == "ラッパー付きテスト"

    def test_to_dict(self) -> None:
        """辞書への変換テスト."""
        decision = ReplanDecision(
            replan_needed=True,
            confidence=0.75,
            reasoning="変換テスト",
            replan_type="retry",
            replan_level=1,
        )
        result = decision.to_dict()
        assert "replan_decision" in result
        inner = result["replan_decision"]
        assert inner["replan_needed"] is True
        assert inner["confidence"] == 0.75
        assert inner["replan_type"] == "retry"

    def test_should_execute(self) -> None:
        """再計画実行判定のテスト."""
        # 再計画が必要で確信度が高い場合
        decision = ReplanDecision(replan_needed=True, confidence=0.8)
        assert decision.should_execute(min_confidence=0.5) is True

        # 再計画が必要だが確信度が低い場合
        decision = ReplanDecision(replan_needed=True, confidence=0.3)
        assert decision.should_execute(min_confidence=0.5) is False

        # 再計画が不要な場合
        decision = ReplanDecision(replan_needed=False, confidence=0.9)
        assert decision.should_execute(min_confidence=0.5) is False

    def test_needs_user_confirmation(self) -> None:
        """ユーザー確認必要判定のテスト."""
        # 明確化が必要な場合
        decision = ReplanDecision(
            clarification_needed=True,
            replan_needed=True,
            confidence=0.9,
        )
        assert decision.needs_user_confirmation() is True

        # 確信度が低い場合
        decision = ReplanDecision(
            clarification_needed=False,
            replan_needed=True,
            confidence=0.2,
        )
        assert decision.needs_user_confirmation(threshold=0.3) is True

        # 確認不要な場合
        decision = ReplanDecision(
            clarification_needed=False,
            replan_needed=True,
            confidence=0.8,
        )
        assert decision.needs_user_confirmation(threshold=0.3) is False


class TestReplanPromptBuilder(unittest.TestCase):
    """ReplanPromptBuilderクラスのテスト."""

    def setUp(self) -> None:
        """テスト環境のセットアップ."""
        self.builder = ReplanPromptBuilder(
            available_tools=["github_read_file", "github_write_file"],
        )

    def test_goal_understanding_prompt(self) -> None:
        """目標の理解フェーズのプロンプト生成テスト."""
        prompt = self.builder.build_goal_understanding_prompt(
            goal_understanding_result={"main_objective": "テスト目標"},
            task_request="テストタスク",
            context_info="テストコンテキスト",
        )
        assert "goal understanding phase" in prompt.lower()
        assert "テスト目標" in prompt
        assert "テストタスク" in prompt
        assert "replan_decision" in prompt

    def test_task_decomposition_prompt(self) -> None:
        """タスク分解フェーズのプロンプト生成テスト."""
        prompt = self.builder.build_task_decomposition_prompt(
            task_decomposition_result={"subtasks": []},
            goal_understanding={"main_objective": "テスト"},
        )
        assert "task decomposition phase" in prompt.lower()
        assert "github_read_file" in prompt

    def test_action_sequence_prompt(self) -> None:
        """行動系列生成フェーズのプロンプト生成テスト."""
        prompt = self.builder.build_action_sequence_prompt(
            action_plan={"actions": []},
            subtasks=[{"id": "task_1"}],
            tool_availability={"github_read_file": True},
        )
        assert "action sequence" in prompt.lower()
        assert "Available" in prompt

    def test_execution_prompt(self) -> None:
        """実行フェーズのプロンプト生成テスト."""
        prompt = self.builder.build_execution_prompt(
            executed_action={"tool": "test"},
            execution_result={"status": "success"},
            error_info="",
            completed_count=1,
            total_count=5,
            error_count=0,
            consecutive_errors=0,
            remaining_actions=[],
        )
        assert "executed an action" in prompt.lower()
        assert "1/5" in prompt

    def test_reflection_prompt(self) -> None:
        """監視と修正フェーズのプロンプト生成テスト."""
        prompt = self.builder.build_reflection_prompt(
            goal_understanding={"main_objective": "テスト"},
            success_criteria=["基準1", "基準2"],
            execution_summary={"status": "success"},
            completed_actions=[],
            current_state="完了",
        )
        assert "completed the execution" in prompt.lower()
        assert "基準1" in prompt


class TestReplanManager(unittest.TestCase):
    """ReplanManagerクラスのテスト."""

    def setUp(self) -> None:
        """テスト環境のセットアップ."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.planning_dir = self.temp_dir / "planning"
        self.planning_dir.mkdir(parents=True, exist_ok=True)
        self.task_uuid = "test-uuid"

        # Create mock history store
        from handlers.planning_history_store import PlanningHistoryStore
        self.history_store = PlanningHistoryStore(self.task_uuid, self.planning_dir)

        self.config = {
            "replanning": {
                "enabled": True,
                "llm_decision": {
                    "min_confidence_threshold": 0.5,
                    "user_confirmation_threshold": 0.3,
                },
                "goal_understanding": {"max_clarification_requests": 2},
                "task_decomposition": {"max_redecomposition_attempts": 3},
                "action_sequence": {"max_regeneration_attempts": 3},
                "execution": {"max_action_retries": 3, "max_partial_replans": 2},
                "reflection": {"max_plan_revisions": 2},
                "global": {
                    "max_total_replans": 10,
                    "infinite_loop_detection": True,
                    "same_trigger_max_count": 2,
                },
            }
        }

        self.manager = ReplanManager(
            config=self.config,
            history_store=self.history_store,
            available_tools=["github_read_file"],
        )

    def tearDown(self) -> None:
        """テスト環境のクリーンアップ."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_manager_creation(self) -> None:
        """ReplanManager生成のテスト."""
        assert self.manager.enabled is True
        assert self.manager.min_confidence == 0.5
        assert self.manager.limits["total"] == 10

    def test_can_replan_initial(self) -> None:
        """初期状態での再計画可能判定テスト."""
        assert self.manager.can_replan("execution", "retry") is True
        assert self.manager.can_replan("reflection", "plan_revision") is True

    def test_can_replan_limit_reached(self) -> None:
        """制限到達時の再計画可能判定テスト."""
        # 総再計画回数を制限まで増やす
        self.manager.replan_counts["total"] = 10
        assert self.manager.can_replan("execution", "retry") is False

    def test_should_override_low_confidence(self) -> None:
        """低確信度時のオーバーライド判定テスト."""
        decision = ReplanDecision(
            replan_needed=True,
            confidence=0.2,  # user_confirmation_threshold (0.3) より低い
            target_phase="execution",
            replan_type="retry",
        )
        should_override, reason = self.manager.should_override(decision)
        assert should_override is True
        assert "確信度" in reason

    def test_should_override_infinite_loop(self) -> None:
        """無限ループ検出時のオーバーライド判定テスト."""
        # 同一トリガーを複数回追加
        trigger_key = "execution:retry"
        self.manager.trigger_history = [trigger_key, trigger_key]

        decision = ReplanDecision(
            replan_needed=True,
            confidence=0.8,
            target_phase="execution",
            replan_type="retry",
        )
        should_override, reason = self.manager.should_override(decision)
        assert should_override is True
        assert "同一トリガー" in reason

    def test_execute_replan_success(self) -> None:
        """再計画実行成功のテスト."""
        decision = ReplanDecision(
            replan_needed=True,
            confidence=0.85,
            target_phase="execution",
            replan_type="retry",
            replan_level=1,
        )
        result = self.manager.execute_replan(decision, "execution")
        assert result is True
        assert self.manager.replan_counts["total"] == 1
        assert self.manager.replan_counts["execution_retry"] == 1

    def test_execute_replan_not_needed(self) -> None:
        """再計画不要時の実行テスト."""
        decision = ReplanDecision(replan_needed=False)
        result = self.manager.execute_replan(decision, "execution")
        assert result is False
        assert self.manager.replan_counts["total"] == 0

    def test_parse_decision_response_json(self) -> None:
        """JSON応答のパーステスト."""
        response = json.dumps({
            "replan_decision": {
                "replan_needed": True,
                "confidence": 0.9,
                "reasoning": "パーステスト",
            }
        })
        decision = self.manager.parse_decision_response(response)
        assert decision.replan_needed is True
        assert decision.confidence == 0.9

    def test_parse_decision_response_dict(self) -> None:
        """辞書応答のパーステスト."""
        response = {
            "replan_decision": {
                "replan_needed": True,
                "confidence": 0.8,
            }
        }
        decision = self.manager.parse_decision_response(response)
        assert decision.replan_needed is True

    def test_parse_decision_response_markdown(self) -> None:
        """マークダウンコードブロック内JSON応答のパーステスト."""
        response = """Some text
```json
{
  "replan_decision": {
    "replan_needed": true,
    "confidence": 0.75
  }
}
```
More text"""
        decision = self.manager.parse_decision_response(response)
        assert decision.replan_needed is True
        assert decision.confidence == 0.75

    def test_record_decision(self) -> None:
        """再計画判断記録のテスト."""
        decision = ReplanDecision(
            replan_needed=True,
            confidence=0.8,
            reasoning="テスト記録",
        )
        self.manager.record_decision("execution", decision, executed=True)

        # 履歴から確認
        decisions = self.history_store.get_replan_decisions()
        assert len(decisions) == 1
        assert decisions[0]["phase"] == "execution"
        assert decisions[0]["executed"] is True

    def test_get_replan_statistics(self) -> None:
        """再計画統計取得のテスト."""
        self.manager.replan_counts["total"] = 5
        self.manager.replan_counts["execution_retry"] = 2

        stats = self.manager.get_replan_statistics()
        assert stats["replan_counts"]["total"] == 5
        assert stats["replan_counts"]["execution_retry"] == 2
        assert stats["enabled"] is True

    def test_reset_counts(self) -> None:
        """カウンターリセットのテスト."""
        self.manager.replan_counts["total"] = 5
        self.manager.trigger_history = ["test:test"]

        self.manager.reset_counts()

        assert self.manager.replan_counts["total"] == 0
        assert len(self.manager.trigger_history) == 0


class TestReplanEnums(unittest.TestCase):
    """列挙型のテスト."""

    def test_replan_type_values(self) -> None:
        """ReplanType列挙型の値テスト."""
        assert ReplanType.CLARIFICATION_REQUEST.value == "clarification_request"
        assert ReplanType.PARTIAL_REPLAN.value == "partial_replan"
        assert ReplanType.NONE.value == "none"

    def test_target_phase_values(self) -> None:
        """TargetPhase列挙型の値テスト."""
        assert TargetPhase.GOAL_UNDERSTANDING.value == "goal_understanding"
        assert TargetPhase.EXECUTION.value == "execution"
        assert TargetPhase.REFLECTION.value == "reflection"

    def test_error_classification_values(self) -> None:
        """ErrorClassification列挙型の値テスト."""
        assert ErrorClassification.TRANSIENT.value == "transient"
        assert ErrorClassification.PERSISTENT.value == "persistent"
        assert ErrorClassification.FATAL.value == "fatal"


if __name__ == "__main__":
    unittest.main()
