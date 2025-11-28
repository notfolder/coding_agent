"""再計画判断のデータクラスモジュール.

LLMが返す再計画判断結果を格納するデータクラスを定義します。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ReplanType(str, Enum):
    """再計画タイプの列挙型.

    各フェーズで発生する再計画のタイプを定義します。
    """

    CLARIFICATION_REQUEST = "clarification_request"  # ユーザーへの明確化要求
    GOAL_REVISION = "goal_revision"  # 目標の再定義
    TASK_REDECOMPOSITION = "task_redecomposition"  # タスクの再分解
    ACTION_REGENERATION = "action_regeneration"  # アクション計画の再生成
    PARTIAL_REPLAN = "partial_replan"  # 部分的な再計画
    FULL_REPLAN = "full_replan"  # 完全な再計画
    PLAN_REVISION = "plan_revision"  # 計画の修正
    RETRY = "retry"  # リトライ
    NONE = "none"  # 再計画不要


class TargetPhase(str, Enum):
    """再計画対象フェーズの列挙型."""

    GOAL_UNDERSTANDING = "goal_understanding"  # 目標の理解
    TASK_DECOMPOSITION = "task_decomposition"  # タスクの分解
    ACTION_SEQUENCE = "action_sequence"  # 行動系列の生成
    EXECUTION = "execution"  # 実行
    REFLECTION = "reflection"  # 監視と修正


class ErrorClassification(str, Enum):
    """エラー分類の列挙型."""

    TRANSIENT = "transient"  # 一時的エラー(ネットワーク、タイムアウト等)
    PERSISTENT = "persistent"  # 永続的エラー
    FATAL = "fatal"  # 致命的エラー


@dataclass
class ReplanDecision:
    """LLMの再計画判断結果を格納するデータクラス.

    Attributes:
        replan_needed: 再計画が必要かどうか
        confidence: 判断の確信度(0.0-1.0)
        reasoning: 判断の理由説明
        replan_type: 再計画タイプ
        target_phase: 再計画開始フェーズ
        replan_level: 再計画レベル(1-5)
        issues_found: 発見された問題のリスト
        recommended_actions: 推奨アクションのリスト
        clarification_needed: ユーザーへの確認が必要か
        clarification_questions: 確認が必要な質問リスト
        error_classification: エラーの分類
        recovery_strategy: 回復戦略の提案
        affected_actions: 影響を受けるアクションのリスト
        evaluation_result: 評価結果(success/partial_success/failure)
        achievement_rate: 目標達成率(0-100)
        additional_actions: 追加が必要なアクションのリスト
        assumptions_to_make: 仮定として進める場合の仮定リスト

    """

    replan_needed: bool = False
    confidence: float = 0.0
    reasoning: str = ""
    replan_type: str = ReplanType.NONE.value
    target_phase: str = ""
    replan_level: int = 0
    issues_found: list[str] = field(default_factory=list)
    recommended_actions: list[str] = field(default_factory=list)
    clarification_needed: bool = False
    clarification_questions: list[str] = field(default_factory=list)
    error_classification: str = ""
    recovery_strategy: str = ""
    affected_actions: list[str] = field(default_factory=list)
    evaluation_result: str = ""
    achievement_rate: int = 0
    additional_actions: list[str] = field(default_factory=list)
    assumptions_to_make: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReplanDecision:
        """辞書からReplanDecisionインスタンスを生成する.

        Args:
            data: LLMからの応答辞書(replan_decisionキーを含む場合はその中身を使用)

        Returns:
            ReplanDecisionインスタンス

        """
        # replan_decision キーがある場合はその中身を使用
        if "replan_decision" in data:
            data = data["replan_decision"]

        return cls(
            replan_needed=data.get("replan_needed", False),
            confidence=data.get("confidence", 0.0),
            reasoning=data.get("reasoning", ""),
            replan_type=data.get("replan_type", ReplanType.NONE.value),
            target_phase=data.get("target_phase", ""),
            replan_level=data.get("replan_level", 0),
            issues_found=data.get("issues_found", []),
            recommended_actions=data.get("recommended_actions", []),
            clarification_needed=data.get("clarification_needed", False),
            clarification_questions=data.get("clarification_questions", []),
            error_classification=data.get("error_classification", ""),
            recovery_strategy=data.get("recovery_strategy", ""),
            affected_actions=data.get("affected_actions", []),
            evaluation_result=data.get("evaluation_result", ""),
            achievement_rate=data.get("achievement_rate", 0),
            additional_actions=data.get("additional_actions", []),
            assumptions_to_make=data.get("assumptions_to_make", []),
        )

    def to_dict(self) -> dict[str, Any]:
        """ReplanDecisionを辞書に変換する.

        Returns:
            辞書形式のデータ

        """
        return {
            "replan_decision": {
                "replan_needed": self.replan_needed,
                "confidence": self.confidence,
                "reasoning": self.reasoning,
                "replan_type": self.replan_type,
                "target_phase": self.target_phase,
                "replan_level": self.replan_level,
                "issues_found": self.issues_found,
                "recommended_actions": self.recommended_actions,
                "clarification_needed": self.clarification_needed,
                "clarification_questions": self.clarification_questions,
                "error_classification": self.error_classification,
                "recovery_strategy": self.recovery_strategy,
                "affected_actions": self.affected_actions,
                "evaluation_result": self.evaluation_result,
                "achievement_rate": self.achievement_rate,
                "additional_actions": self.additional_actions,
                "assumptions_to_make": self.assumptions_to_make,
            },
        }

    def should_execute(self, min_confidence: float = 0.5) -> bool:
        """再計画を実行すべきかを判定する.

        Args:
            min_confidence: 最小確信度閾値

        Returns:
            再計画を実行すべきかどうか

        """
        return self.replan_needed and self.confidence >= min_confidence

    def needs_user_confirmation(self, threshold: float = 0.3) -> bool:
        """ユーザー確認が必要かを判定する.

        Args:
            threshold: ユーザー確認を要求する確信度の閾値

        Returns:
            ユーザー確認が必要かどうか

        """
        # 明確化が必要な場合、または確信度が低い場合
        return self.clarification_needed or (
            self.replan_needed and self.confidence < threshold
        )
