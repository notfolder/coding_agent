"""再計画管理モジュール.

LLMによる再計画判断を管理するReplanManagerクラスを定義します。
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from handlers.replan_decision import ReplanDecision, ReplanType, TargetPhase
from handlers.replan_prompt_builder import ReplanPromptBuilder

if TYPE_CHECKING:
    from clients.llm_base import LLMClient
    from handlers.planning_history_store import PlanningHistoryStore


class ReplanManager:
    """LLMによる再計画判断を管理するクラス.

    各フェーズでの再計画判断の依頼、応答のパース、
    再計画の実行制御、履歴の記録を担当します。
    """

    def __init__(
        self,
        config: dict[str, Any],
        history_store: PlanningHistoryStore,
        available_tools: list[str] | None = None,
    ) -> None:
        """ReplanManagerを初期化する.

        Args:
            config: 再計画設定
            history_store: 計画履歴ストア
            available_tools: 利用可能なツールのリスト

        """
        self.config = config
        self.history_store = history_store
        self.logger = logging.getLogger(__name__)

        # プロンプトビルダーを初期化
        self.prompt_builder = ReplanPromptBuilder(available_tools)

        # 再計画回数カウンター
        self.replan_counts = {
            "goal_understanding": 0,
            "task_decomposition": 0,
            "action_sequence": 0,
            "execution_retry": 0,
            "execution_partial": 0,
            "reflection": 0,
            "total": 0,
        }

        # 無限ループ検出用の履歴
        self.trigger_history: list[str] = []

        # 設定値の取得
        replanning_config = config.get("replanning", {})
        self.enabled = replanning_config.get("enabled", True)

        # LLM判断設定
        llm_decision_config = replanning_config.get("llm_decision", {})
        self.min_confidence = llm_decision_config.get("min_confidence_threshold", 0.5)
        self.user_confirmation_threshold = llm_decision_config.get(
            "user_confirmation_threshold", 0.3,
        )

        # 各フェーズの制限
        self.limits = {
            "goal_understanding": replanning_config.get("goal_understanding", {}).get(
                "max_clarification_requests", 2,
            ),
            "task_decomposition": replanning_config.get("task_decomposition", {}).get(
                "max_redecomposition_attempts", 3,
            ),
            "action_sequence": replanning_config.get("action_sequence", {}).get(
                "max_regeneration_attempts", 3,
            ),
            "execution_retry": replanning_config.get("execution", {}).get(
                "max_action_retries", 3,
            ),
            "execution_partial": replanning_config.get("execution", {}).get(
                "max_partial_replans", 2,
            ),
            "reflection": replanning_config.get("reflection", {}).get(
                "max_plan_revisions", 2,
            ),
            "total": replanning_config.get("global", {}).get("max_total_replans", 10),
        }

        # 無限ループ検出設定
        global_config = replanning_config.get("global", {})
        self.infinite_loop_detection = global_config.get(
            "infinite_loop_detection", True,
        )
        self.same_trigger_max_count = global_config.get("same_trigger_max_count", 2)

    def request_llm_decision(
        self,
        llm_client: LLMClient,
        phase: str,
        context: dict[str, Any],
    ) -> ReplanDecision:
        """LLMに再計画判断を依頼する.

        Args:
            llm_client: LLMクライアント
            phase: 現在のフェーズ
            context: フェーズに応じたコンテキスト情報

        Returns:
            ReplanDecisionインスタンス

        """
        if not self.enabled:
            self.logger.debug("再計画機能が無効です")
            return ReplanDecision()

        # フェーズに応じたプロンプトを生成
        prompt = self._build_prompt_for_phase(phase, context)
        if not prompt:
            self.logger.warning("フェーズ %s のプロンプト生成に失敗しました", phase)
            return ReplanDecision()

        # LLMに判断を依頼
        try:
            llm_client.send_user_message(prompt)
            response, _, tokens = llm_client.get_response()
            self.logger.info(
                "再計画判断LLM応答を受信しました (tokens: %d)", tokens,
            )

            # 応答をパース
            decision = self.parse_decision_response(response)

            # 判断を記録
            self.record_decision(phase, decision)

        except Exception:
            self.logger.exception("再計画判断の依頼に失敗しました")
            return ReplanDecision()

        return decision

    def parse_decision_response(self, response: str | dict[str, Any]) -> ReplanDecision:
        """LLM応答をパースしてReplanDecisionに変換する.

        Args:
            response: LLMからの応答

        Returns:
            ReplanDecisionインスタンス

        """
        try:
            # 辞書の場合はそのまま使用
            if isinstance(response, dict):
                return ReplanDecision.from_dict(response)

            # 文字列の場合はJSONをパース
            # <think></think>タグを除去
            cleaned_response = re.sub(
                r"<think>.*?</think>", "", response, flags=re.DOTALL,
            )
            cleaned_response = cleaned_response.strip()

            # JSONをパース
            try:
                data = json.loads(cleaned_response)
                return ReplanDecision.from_dict(data)
            except json.JSONDecodeError:
                # マークダウンコードブロックからJSON抽出を試行
                json_match = re.search(
                    r"```(?:json)?\s*(\{.*?\})\s*```",
                    cleaned_response,
                    re.DOTALL,
                )
                if json_match:
                    data = json.loads(json_match.group(1))
                    return ReplanDecision.from_dict(data)

                # テキスト内のJSONオブジェクトを検索
                json_match = re.search(r"\{.*\}", cleaned_response, re.DOTALL)
                if json_match:
                    data = json.loads(json_match.group(0))
                    return ReplanDecision.from_dict(data)

                raise

        except (json.JSONDecodeError, AttributeError):
            self.logger.warning(
                "再計画判断応答のパースに失敗しました: %s",
                str(response)[:200],
            )
            return ReplanDecision()

    def can_replan(self, phase: str, replan_type: str = "") -> bool:
        """再計画可能かを判定する.

        Args:
            phase: 現在のフェーズ
            replan_type: 再計画タイプ

        Returns:
            再計画可能かどうか

        """
        if not self.enabled:
            return False

        # 総再計画回数のチェック
        if self.replan_counts["total"] >= self.limits["total"]:
            self.logger.warning("総再計画回数の制限に達しました")
            return False

        # フェーズ別の制限チェック
        phase_key = phase
        if phase == "execution":
            phase_key = (
                "execution_retry"
                if replan_type == ReplanType.RETRY.value
                else "execution_partial"
            )

        if (
            phase_key in self.replan_counts
            and phase_key in self.limits
            and self.replan_counts[phase_key] >= self.limits[phase_key]
        ):
            self.logger.warning(
                "フェーズ %s の再計画回数制限に達しました", phase_key,
            )
            return False

        return True

    def should_override(self, decision: ReplanDecision) -> tuple[bool, str]:
        """LLM判断をオーバーライドすべきかを判定する.

        Args:
            decision: LLMの再計画判断

        Returns:
            (オーバーライドすべきか, 理由)のタプル

        """
        # 再計画不要の場合はオーバーライド不要
        if not decision.replan_needed:
            return False, ""

        # 確信度が低すぎる場合
        if decision.confidence < self.user_confirmation_threshold:
            return True, f"確信度が低すぎます ({decision.confidence:.2f})"

        # 無限ループ検出
        if self.infinite_loop_detection:
            trigger_key = f"{decision.target_phase}:{decision.replan_type}"
            trigger_count = self.trigger_history.count(trigger_key)
            if trigger_count >= self.same_trigger_max_count:
                return True, f"同一トリガーでの再計画が{trigger_count}回検出されました"

        return False, ""

    def execute_replan(
        self,
        decision: ReplanDecision,
        phase: str,
    ) -> bool:
        """再計画を実行する.

        Args:
            decision: LLMの再計画判断
            phase: 現在のフェーズ

        Returns:
            再計画を実行するかどうか

        """
        if not decision.replan_needed:
            return False

        # 再計画可能かチェック
        if not self.can_replan(phase, decision.replan_type):
            self.logger.warning(
                "再計画制限により実行をスキップします: phase=%s", phase,
            )
            return False

        # オーバーライドチェック
        should_override, reason = self.should_override(decision)
        if should_override:
            self.logger.warning("再計画をオーバーライドします: %s", reason)
            return False

        # 確信度チェック
        if decision.confidence < self.min_confidence:
            self.logger.warning(
                "確信度が閾値未満のため再計画をスキップします "
                "(confidence=%.2f, threshold=%s)",
                decision.confidence,
                self.min_confidence,
            )
            return False

        # カウンターを更新
        self._update_replan_counts(phase, decision.replan_type)

        # トリガー履歴を更新
        trigger_key = f"{decision.target_phase}:{decision.replan_type}"
        self.trigger_history.append(trigger_key)

        self.logger.info(
            "再計画を実行します: type=%s, target_phase=%s, level=%d",
            decision.replan_type,
            decision.target_phase,
            decision.replan_level,
        )

        return True

    def record_decision(
        self,
        phase: str,
        decision: ReplanDecision,
        *,
        executed: bool = False,
        override_reason: str = "",
    ) -> None:
        """再計画判断を履歴に記録する.

        Args:
            phase: 判断が行われたフェーズ
            decision: LLMの再計画判断
            executed: 実際に再計画が実行されたか
            override_reason: オーバーライドされた場合の理由

        """
        entry = {
            "type": "replan_decision",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "phase": phase,
            "llm_decision": decision.to_dict(),
            "confidence": decision.confidence,
            "executed": executed,
            "override_reason": override_reason,
            "replan_counts": dict(self.replan_counts),
        }

        # PlanningHistoryStoreに記録
        self.history_store.save_replan_decision(entry)
        self.logger.debug(
            "再計画判断を記録しました: phase=%s, executed=%s",
            phase,
            executed,
        )

    def get_replan_statistics(self) -> dict[str, Any]:
        """再計画統計を取得する.

        Returns:
            再計画統計の辞書

        """
        return {
            "replan_counts": dict(self.replan_counts),
            "limits": dict(self.limits),
            "trigger_history_count": len(self.trigger_history),
            "enabled": self.enabled,
        }

    def reset_counts(self) -> None:
        """再計画カウンターをリセットする."""
        for key in self.replan_counts:
            self.replan_counts[key] = 0
        self.trigger_history = []
        self.logger.info("再計画カウンターをリセットしました")

    def _build_prompt_for_phase(
        self,
        phase: str,
        context: dict[str, Any],
    ) -> str:
        """フェーズに応じたプロンプトを生成する.

        Args:
            phase: 現在のフェーズ
            context: コンテキスト情報

        Returns:
            プロンプト文字列

        """
        if phase == TargetPhase.GOAL_UNDERSTANDING.value:
            return self.prompt_builder.build_goal_understanding_prompt(
                goal_understanding_result=context.get("goal_understanding_result", {}),
                task_request=context.get("task_request", ""),
                context_info=context.get("context_info", ""),
            )

        if phase == TargetPhase.TASK_DECOMPOSITION.value:
            return self.prompt_builder.build_task_decomposition_prompt(
                task_decomposition_result=context.get("task_decomposition_result", {}),
                goal_understanding=context.get("goal_understanding", {}),
            )

        if phase == TargetPhase.ACTION_SEQUENCE.value:
            return self.prompt_builder.build_action_sequence_prompt(
                action_plan=context.get("action_plan", {}),
                subtasks=context.get("subtasks", []),
                tool_availability=context.get("tool_availability"),
            )

        if phase == TargetPhase.EXECUTION.value:
            return self.prompt_builder.build_execution_prompt(
                executed_action=context.get("executed_action", {}),
                execution_result=context.get("execution_result", {}),
                error_info=context.get("error_info", ""),
                completed_count=context.get("completed_count", 0),
                total_count=context.get("total_count", 0),
                error_count=context.get("error_count", 0),
                consecutive_errors=context.get("consecutive_errors", 0),
                remaining_actions=context.get("remaining_actions"),
            )

        if phase == TargetPhase.REFLECTION.value:
            return self.prompt_builder.build_reflection_prompt(
                goal_understanding=context.get("goal_understanding", {}),
                success_criteria=context.get("success_criteria", []),
                execution_summary=context.get("execution_summary", {}),
                completed_actions=context.get("completed_actions", []),
                current_state=context.get("current_state", ""),
            )

        self.logger.warning("未知のフェーズ: %s", phase)
        return ""

    def _update_replan_counts(self, phase: str, replan_type: str) -> None:
        """再計画カウンターを更新する.

        Args:
            phase: フェーズ
            replan_type: 再計画タイプ

        """
        # 総カウントを更新
        self.replan_counts["total"] += 1

        # フェーズ別カウントを更新
        phase_key = phase
        if phase == "execution":
            phase_key = (
                "execution_retry"
                if replan_type == ReplanType.RETRY.value
                else "execution_partial"
            )

        if phase_key in self.replan_counts:
            self.replan_counts[phase_key] += 1
