"""計画前情報収集フェーズを管理するマネージャーモジュール.

このモジュールは、計画を立てる前に依頼内容を理解し、必要な情報を収集するための
「計画前情報収集フェーズ」を実装します。
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from clients.llm_base import LLMClient
    from clients.mcp_tool_client import MCPToolClient
    from handlers.task import Task

# 文字列切り詰め制限定数
SUMMARY_TRUNCATION_LIMIT = 500  # 収集データのサマリー切り詰め文字数
TEXT_TRUNCATION_LIMIT = 100  # 通知用テキスト切り詰め文字数


class PrePlanningManager:
    """計画前情報収集フェーズを管理するマネージャークラス.

    3つのサブフェーズを制御・調整し、計画フェーズへの引き継ぎデータを生成します：
    - 依頼内容の理解
    - 情報収集計画
    - 情報収集の実行
    """

    def __init__(
        self,
        config: dict[str, Any],
        llm_client: LLMClient,
        mcp_clients: dict[str, MCPToolClient],
        task: Task,
        progress_manager: Any | None = None,
    ) -> None:
        """PrePlanningManagerを初期化する.

        Args:
            config: 計画前情報収集の設定（planning.pre_planning配下）
            llm_client: LLMクライアントインスタンス
            mcp_clients: MCPツールクライアントの辞書
            task: 処理対象のタスクオブジェクト
            progress_manager: 進捗コメントマネージャ（オプション）

        """
        self.config = config
        self.llm_client = llm_client
        self.mcp_clients = mcp_clients
        self.task = task
        self.logger = logging.getLogger(__name__)
        self.progress_manager = progress_manager

        # 設定の読み込み
        self.understanding_config = config.get("understanding", {})
        self.collection_config = config.get("collection", {})
        self.assumption_config = config.get("assumption", {})
        self.notification_config = config.get("notification", {})

        # 結果の保持
        self.understanding_result: dict[str, Any] | None = None
        self.collection_plan: dict[str, Any] | None = None
        self.collection_results: list[dict[str, Any]] = []
        self.assumptions: list[dict[str, Any]] = []
        self.information_gaps: list[dict[str, Any]] = []

        # 現在のサブフェーズ
        self.current_subphase = "understanding"

        # コンテキストマネージャ（統計更新用）
        self.context_manager: Any = None

    def execute(self) -> dict[str, Any]:
        """計画前情報収集フェーズ全体を実行する.

        Returns:
            計画フェーズへの引き継ぎデータ

        """
        self.logger.info("計画前情報収集フェーズを開始します")

        # 開始通知
        if self.notification_config.get("notify_on_start", True):
            self._post_start_notification()

        # 1. 依頼内容の理解
        self.current_subphase = "understanding"
        self.understanding_result = self.execute_understanding()

        # 理解完了通知
        if self.notification_config.get("notify_on_understanding_complete", True):
            self._post_understanding_complete_notification()

        # 2. 情報収集計画の生成
        self.current_subphase = "collection_planning"
        self.collection_plan = self.execute_collection_planning()

        # 3. 情報収集の実行（スキップでない場合）
        if self.collection_plan and not self.collection_plan.get(
            "information_needs", {},
        ).get("skip_collection", False):
            self.current_subphase = "collection"
            if self.collection_config.get("enabled", True):
                self.collection_results = self.execute_collection()

                # 4. 推測による補完（必要な場合）
                if self.assumption_config.get("enabled", True):
                    self.current_subphase = "assumption"
                    self.make_assumptions()

        # 収集完了通知
        if self.notification_config.get("notify_on_collection_complete", True):
            self._post_collection_complete_notification()

        self.logger.info("計画前情報収集フェーズが完了しました")

        return self.get_result()

    def execute_understanding(self) -> dict[str, Any]:
        """依頼内容の理解サブフェーズを実行する.

        Returns:
            依頼内容の理解結果

        """
        self.logger.info("依頼内容の理解サブフェーズを開始します")

        # タスク情報を取得
        task_info = self.task.get_prompt()

        # 過去の実行履歴を取得（利用可能な場合）
        past_history = self._get_past_history()

        # LLMへのプロンプトを構築
        prompt = self._build_understanding_prompt(task_info, past_history)

        # LLMに依頼
        self.llm_client.send_user_message(prompt)
        response, _, tokens = self.llm_client.get_response()
        self.logger.info("依頼内容の理解LLM応答 (トークン数: %d)", tokens)

        # トークン数を記録
        if self.context_manager:
            self.context_manager.update_statistics(llm_calls=1, tokens=tokens)

        # レスポンスをパース
        result = self._parse_understanding_response(response)

        if result is None:
            # パースに失敗した場合は最小限の理解結果を返す
            self.logger.warning("依頼内容の理解レスポンスのパースに失敗しました")
            result = self._create_minimal_understanding(task_info)

        return result

    def execute_collection_planning(self) -> dict[str, Any]:
        """情報収集計画サブフェーズを実行する.

        Returns:
            情報収集計画

        """
        self.logger.info("情報収集計画サブフェーズを開始します")

        if not self.understanding_result:
            self.logger.warning("依頼内容の理解結果がありません")
            return {"information_needs": {"skip_collection": True, "skip_reason": "理解結果なし"}}

        # LLMへのプロンプトを構築
        prompt = self._build_collection_planning_prompt()

        # LLMに依頼
        self.llm_client.send_user_message(prompt)
        response, _, tokens = self.llm_client.get_response()
        self.logger.info("情報収集計画LLM応答 (トークン数: %d)", tokens)

        # トークン数を記録
        if self.context_manager:
            self.context_manager.update_statistics(llm_calls=1, tokens=tokens)

        # レスポンスをパース
        result = self._parse_collection_planning_response(response)

        if result is None:
            # パースに失敗した場合は収集スキップ
            self.logger.warning("情報収集計画レスポンスのパースに失敗しました")
            return {"information_needs": {"skip_collection": True, "skip_reason": "計画生成失敗"}}

        return result

    def execute_collection(self) -> list[dict[str, Any]]:
        """情報収集実行サブフェーズを実行する.

        Returns:
            収集結果のリスト

        """
        self.logger.info("情報収集実行サブフェーズを開始します")

        if not self.collection_plan:
            return []

        information_needs = self.collection_plan.get("information_needs", {})
        required_info = information_needs.get("required_information", [])
        collection_order = information_needs.get("collection_order", [])

        if not required_info:
            self.logger.info("収集対象の情報がありません")
            return []

        results = []
        max_retries = self.collection_config.get("max_retries_per_tool", 2)

        # 収集順序に従って実行
        ordered_info = self._order_by_collection_order(required_info, collection_order)

        for info_item in ordered_info:
            info_id = info_item.get("id", "unknown")
            self.logger.info("情報収集: %s", info_id)

            result = self._collect_single_item(info_item, max_retries)
            results.append(result)

        return results

    def make_assumptions(self) -> None:
        """情報不足時の推測処理を実行する.

        収集に失敗した項目について推測を行い、self.assumptionsに追加する。
        """
        self.logger.info("推測処理を開始します")

        failed_items = [
            r for r in self.collection_results if r.get("status") == "failed"
        ]

        if not failed_items:
            self.logger.info("推測対象の項目がありません")
            return

        confidence_threshold = self.assumption_config.get("confidence_threshold", 0.5)

        for failed_item in failed_items:
            info_id = failed_item.get("info_id", "unknown")

            # 推測不可項目のチェック
            if self._is_non_assumable(info_id):
                self.logger.info("推測不可項目: %s", info_id)
                self._add_information_gap(info_id, "セキュリティに関わる設定のため推測不可")
                continue

            # 対応する収集計画の項目を取得
            plan_item = self._find_plan_item(info_id)
            if not plan_item or not plan_item.get("can_assume", True):
                self._add_information_gap(info_id, "推測不可と指定されている")
                continue

            # LLMに推測を依頼
            assumption = self._make_single_assumption(failed_item, plan_item)

            if assumption:
                confidence = assumption.get("confidence", 0.0)
                if confidence >= confidence_threshold:
                    self.assumptions.append(assumption)
                    # 推測通知（任意）
                    if self.notification_config.get("notify_on_assumption", False):
                        self._post_assumption_notification(assumption)
                else:
                    # 確信度が低い場合は情報ギャップとして記録
                    self._add_information_gap(
                        info_id, f"推測の確信度が低い ({confidence:.2f})"
                    )

    def get_result(self) -> dict[str, Any]:
        """計画フェーズへの引き継ぎデータを取得する.

        Returns:
            計画フェーズへの引き継ぎデータ

        """
        # 収集した情報をカテゴリ別に整理
        collected_information = self._organize_collected_information()

        # 計画への推奨事項を生成
        recommendations = self._generate_recommendations()

        return {
            "pre_planning_result": {
                "request_understanding": self._extract_understanding_summary(),
                "collected_information": collected_information,
                "assumptions": self.assumptions,
                "information_gaps": self.information_gaps,
                "recommendations_for_planning": recommendations,
            }
        }

    def get_pre_planning_state(self) -> dict[str, Any]:
        """一時停止用の状態を取得する.

        Returns:
            計画前情報収集フェーズの状態

        """
        return {
            "current_subphase": self.current_subphase,
            "understanding_result": self.understanding_result,
            "collection_plan": self.collection_plan,
            "collection_results": self.collection_results,
            "assumptions": self.assumptions,
            "information_gaps": self.information_gaps,
        }

    def restore_pre_planning_state(self, state: dict[str, Any]) -> None:
        """一時停止からの復元時に状態を復元する.

        Args:
            state: 保存された状態

        """
        self.current_subphase = state.get("current_subphase", "understanding")
        self.understanding_result = state.get("understanding_result")
        self.collection_plan = state.get("collection_plan")
        self.collection_results = state.get("collection_results", [])
        self.assumptions = state.get("assumptions", [])
        self.information_gaps = state.get("information_gaps", [])

    # プライベートメソッド

    def _get_past_history(self) -> list[dict[str, Any]]:
        """過去の実行履歴を取得する.

        Returns:
            過去の実行履歴リスト

        """
        # 現在の実装では空リストを返す（将来的にはhistory_storeから取得）
        return []

    def _build_understanding_prompt(
        self, task_info: str, past_history: list[dict[str, Any]]
    ) -> str:
        """依頼内容の理解用プロンプトを構築する.

        Args:
            task_info: タスク情報
            past_history: 過去の実行履歴

        Returns:
            プロンプト文字列

        """
        prompt_parts = [
            "以下のタスク内容を分析し、依頼内容を正確に理解してください。",
            "",
            "=== タスク情報 ===",
            task_info,
            "",
        ]

        if past_history:
            prompt_parts.extend([
                "=== 過去の実行履歴 ===",
                json.dumps(past_history, indent=2, ensure_ascii=False),
                "",
            ])

        prompt_parts.extend([
            "=== 理解すべき項目 ===",
            "1. タスクの種類（新機能開発、バグ修正、リファクタリング等）",
            "2. 主な目標（達成すべき最終的な状態）",
            "3. 期待される成果物（具体的な出力物）",
            "4. 制約条件（技術的・時間的な制約）",
            "5. スコープ（タスクの範囲と境界）",
            "",
            "曖昧な点がある場合は、最も妥当な解釈を選択し、その理由を説明してください。",
            "",
            "以下のJSON形式で応答してください：",
            "```json",
            "{",
            '  "phase": "request_understanding",',
            '  "request_understanding": {',
            '    "task_type": "タスクの種類",',
            '    "primary_goal": "主な目標",',
            '    "expected_deliverables": ["成果物1", "成果物2"],',
            '    "constraints": ["制約1", "制約2"],',
            '    "scope": {',
            '      "in_scope": ["スコープ内"],',
            '      "out_of_scope": ["スコープ外"]',
            "    },",
            '    "understanding_confidence": 0.85,',
            '    "ambiguities": []',
            "  }",
            "}",
            "```",
        ])

        return "\n".join(prompt_parts)

    def _build_collection_planning_prompt(self) -> str:
        """情報収集計画用プロンプトを構築する.

        Returns:
            プロンプト文字列

        """
        understanding_summary = json.dumps(
            self.understanding_result, indent=2, ensure_ascii=False
        )

        # 利用可能なツールのリストを取得
        available_tools = self._get_available_tools_list()

        prompt_parts = [
            "以下の理解に基づいて、計画を立てるために必要な情報を特定してください。",
            "",
            "=== 依頼内容の理解結果 ===",
            understanding_summary,
            "",
            "=== 利用可能なツール ===",
            available_tools,
            "",
            "=== 収集対象となる情報カテゴリ ===",
            "1. codebase: プロジェクト構造、関連コード、依存関係、テスト構造、設定ファイル",
            "2. context: 既存実装パターン、コーディング規約、APIドキュメント",
            "3. external: 関連Issue/PR、外部ドキュメント",
            "",
            "タスクが非常にシンプルな場合や、追加情報が不要な場合は、skip_collectionをtrueにしてください。",
            "",
            "**重要**: collection_methodのtoolフィールドには、上記「利用可能なツール」に記載された正確なツール名を使用してください。",
            "",
            "以下のJSON形式で応答してください：",
            "```json",
            "{",
            '  "phase": "information_planning",',
            '  "information_needs": {',
            '    "required_information": [',
            "      {",
            '        "id": "info_1",',
            '        "category": "codebase",',
            '        "description": "収集する情報の説明",',
            '        "purpose": "この情報が必要な理由",',
            '        "collection_method": {',
            '          "tool": "ツール名",',
            '          "parameters": {}',
            "        },",
            '        "fallback_strategy": "収集できない場合の対処",',
            '        "can_assume": true,',
            '        "default_assumption": "推測する場合のデフォルト値"',
            "      }",
            "    ],",
            '    "collection_order": ["info_1"],',
            '    "skip_collection": false,',
            '    "skip_reason": ""',
            "  }",
            "}",
            "```",
        ]

        return "\n".join(prompt_parts)

    def _parse_understanding_response(self, response: str) -> dict[str, Any] | None:
        """依頼内容の理解レスポンスをパースする.

        Args:
            response: LLMからの応答文字列

        Returns:
            パースされた辞書、またはNone

        """
        return self._parse_json_response(response)

    def _parse_collection_planning_response(
        self, response: str
    ) -> dict[str, Any] | None:
        """情報収集計画レスポンスをパースする.

        Args:
            response: LLMからの応答文字列

        Returns:
            パースされた辞書、またはNone

        """
        return self._parse_json_response(response)

    def _parse_json_response(self, response: str) -> dict[str, Any] | None:
        """JSONレスポンスをパースする.

        Args:
            response: LLMからの応答文字列

        Returns:
            パースされた辞書、またはNone

        """
        try:
            if isinstance(response, dict):
                return response

            # <think></think>タグを削除
            response = re.sub(r"<think>.*?</think>", "", response, flags=re.DOTALL)
            response = response.strip()

            # JSONとしてパース
            try:
                return json.loads(response)
            except json.JSONDecodeError:
                # Markdownコードブロックから抽出を試みる
                json_match = re.search(
                    r"```(?:json)?\s*(\{.*?\})\s*```", response, re.DOTALL
                )
                if json_match:
                    return json.loads(json_match.group(1))

                # テキスト内のJSONオブジェクトを探す
                json_match = re.search(r"\{.*\}", response, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group(0))

                raise

        except (json.JSONDecodeError, AttributeError):
            self.logger.warning(
                "JSONレスポンスのパースに失敗しました: %s", response[:200]
            )
            return None

    def _create_minimal_understanding(self, task_info: str) -> dict[str, Any]:
        """最小限の理解結果を作成する.

        Args:
            task_info: タスク情報

        Returns:
            最小限の理解結果

        """
        return {
            "phase": "request_understanding",
            "request_understanding": {
                "task_type": "unknown",
                "primary_goal": task_info[:200] if task_info else "不明",
                "expected_deliverables": [],
                "constraints": [],
                "scope": {"in_scope": [], "out_of_scope": []},
                "understanding_confidence": 0.3,
                "ambiguities": [
                    {
                        "item": "タスク内容全体",
                        "possible_interpretations": ["詳細不明"],
                        "selected_interpretation": "情報不足のため推測で進行",
                        "reasoning": "LLM応答のパースに失敗したため",
                    }
                ],
            },
        }

    def _order_by_collection_order(
        self, required_info: list[dict[str, Any]], collection_order: list[str]
    ) -> list[dict[str, Any]]:
        """収集順序に従ってリストを並び替える.

        Args:
            required_info: 収集対象情報のリスト
            collection_order: 収集順序のIDリスト

        Returns:
            並び替えられたリスト

        """
        if not collection_order:
            return required_info

        # IDでインデックス化
        info_by_id = {item.get("id"): item for item in required_info}

        ordered = []
        for info_id in collection_order:
            if info_id in info_by_id:
                ordered.append(info_by_id.pop(info_id))

        # 順序リストに含まれない項目は最後に追加
        ordered.extend(info_by_id.values())

        return ordered

    def _collect_single_item(
        self, info_item: dict[str, Any], max_retries: int
    ) -> dict[str, Any]:
        """単一の情報項目を収集する.

        Args:
            info_item: 収集対象の情報項目
            max_retries: 最大リトライ回数

        Returns:
            収集結果

        """
        info_id = info_item.get("id", "unknown")
        collection_method = info_item.get("collection_method", {})
        tool_name = collection_method.get("tool", "")
        parameters = collection_method.get("parameters", {})

        result = {
            "info_id": info_id,
            "status": "failed",
            "collected_data": None,
            "assumption_made": None,
            "tool_calls_used": 0,
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        }

        if not tool_name:
            self.logger.warning("ツールが指定されていません: %s", info_id)
            return result

        # MCPサーバー名とツール名を分離
        mcp_server, actual_tool = self._parse_tool_name(tool_name)

        if mcp_server not in self.mcp_clients:
            self.logger.warning("MCPクライアントが見つかりません: %s in %s", mcp_server, self.mcp_clients.keys())
            return result

        mcp_client = self.mcp_clients[mcp_server]

        # リトライ付きでツールを呼び出し
        for attempt in range(max_retries + 1):
            result["tool_calls_used"] = attempt + 1
            try:
                tool_result = mcp_client.call_tool(actual_tool, parameters)
                result["status"] = "collected"
                result["collected_data"] = {
                    "summary": str(tool_result)[:SUMMARY_TRUNCATION_LIMIT],
                    "details": tool_result,
                }
                self.logger.info("情報収集成功: %s (試行 %d)", info_id, attempt + 1)
                return result
            except Exception as e:
                self.logger.warning(
                    "情報収集失敗: %s (試行 %d): %s", info_id, attempt + 1, e
                )
                if attempt >= max_retries:
                    break

        return result

    def _get_available_tools_list(self) -> str:
        """利用可能なツールのリストを取得する.

        Returns:
            ツールリストの文字列

        """
        tools_info = []
        
        for mcp_name, mcp_client in self.mcp_clients.items():
            try:
                # Get function definitions from MCP client
                functions = mcp_client.get_function_calling_functions()
                
                if functions:
                    tools_info.append(f"\n**{mcp_name} MCP:**")
                    for func in functions:
                        tool_name = func.get("name", "unknown")
                        description = func.get("description", "説明なし")
                        tools_info.append(f"- `{tool_name}`: {description}")
            except Exception as e:
                self.logger.warning("MCPクライアント %s からツール情報を取得できませんでした: %s", mcp_name, e)
        
        if not tools_info:
            return "利用可能なツールがありません"
        
        return "\n".join(tools_info)

    def _parse_tool_name(self, tool_name: str) -> tuple[str, str]:
        """ツール名からMCPサーバー名と実際のツール名を分離する.

        Args:
            tool_name: ツール名

        Returns:
            (MCPサーバー名, 実際のツール名)

        """
        if "_" in tool_name:
            parts = tool_name.split("_", 1)
            return parts[0], parts[1]
        return "default", tool_name

    def _is_non_assumable(self, info_id: str) -> bool:
        """推測不可な項目かどうかを判定する.

        Args:
            info_id: 情報ID

        Returns:
            推測不可の場合True

        """
        non_assumable_keywords = [
            "security",
            "secret",
            "password",
            "token",
            "api_key",
            "credential",
            "database",
            "connection_string",
            "pii",
            "personal_info",
        ]

        info_id_lower = info_id.lower()
        return any(keyword in info_id_lower for keyword in non_assumable_keywords)

    def _find_plan_item(self, info_id: str) -> dict[str, Any] | None:
        """収集計画から対応する項目を検索する.

        Args:
            info_id: 情報ID

        Returns:
            対応する計画項目、またはNone

        """
        if not self.collection_plan:
            return None

        required_info = self.collection_plan.get("information_needs", {}).get(
            "required_information", []
        )

        for item in required_info:
            if item.get("id") == info_id:
                return item

        return None

    def _make_single_assumption(
        self, failed_item: dict[str, Any], plan_item: dict[str, Any]
    ) -> dict[str, Any] | None:
        """単一の項目について推測を行う.

        Args:
            failed_item: 収集に失敗した結果
            plan_item: 対応する計画項目

        Returns:
            推測結果、またはNone

        """
        info_id = failed_item.get("info_id", "unknown")

        # デフォルト推測値がある場合はそれを使用
        default_assumption = plan_item.get("default_assumption")
        if default_assumption:
            return {
                "info_id": info_id,
                "assumed_value": default_assumption,
                "reasoning": "収集計画で定義されたデフォルト値を使用",
                "confidence": 0.7,
            }

        # LLMに推測を依頼
        prompt = self._build_assumption_prompt(failed_item, plan_item)
        self.llm_client.send_user_message(prompt)
        response, _, tokens = self.llm_client.get_response()

        # トークン数を記録
        if self.context_manager:
            self.context_manager.update_statistics(llm_calls=1, tokens=tokens)

        # レスポンスをパース
        result = self._parse_json_response(response)

        if result and "assumption" in result:
            return result["assumption"]

        return None

    def _build_assumption_prompt(
        self, failed_item: dict[str, Any], plan_item: dict[str, Any]
    ) -> str:
        """推測用プロンプトを構築する.

        Args:
            failed_item: 収集に失敗した結果
            plan_item: 対応する計画項目

        Returns:
            プロンプト文字列

        """
        prompt_parts = [
            "以下の情報を収集できませんでした。合理的な推測を行ってください。",
            "",
            f"情報ID: {plan_item.get('id', 'unknown')}",
            f"説明: {plan_item.get('description', '')}",
            f"目的: {plan_item.get('purpose', '')}",
            f"フォールバック戦略: {plan_item.get('fallback_strategy', '')}",
            "",
            "以下のJSON形式で応答してください：",
            "```json",
            "{",
            '  "assumption": {',
            f'    "info_id": "{plan_item.get("id", "unknown")}",',
            '    "assumed_value": "推測した値",',
            '    "reasoning": "推測の根拠",',
            '    "confidence": 0.6',
            "  }",
            "}",
            "```",
        ]

        return "\n".join(prompt_parts)

    def _add_information_gap(self, info_id: str, reason: str) -> None:
        """情報ギャップを追加する.

        Args:
            info_id: 情報ID
            reason: ギャップの理由

        """
        # 対応する計画項目を取得して影響を評価
        plan_item = self._find_plan_item(info_id)
        impact = "計画への影響は不明"
        if plan_item:
            impact = f"目的: {plan_item.get('purpose', '不明')}"

        self.information_gaps.append({
            "description": f"{info_id}: {reason}",
            "impact": impact,
        })

    def _organize_collected_information(self) -> dict[str, Any]:
        """収集した情報をカテゴリ別に整理する.

        Returns:
            カテゴリ別に整理された情報

        """
        organized: dict[str, dict[str, Any]] = {
            "codebase": {},
            "context": {},
            "external": {},
        }

        if not self.collection_plan:
            return organized

        required_info = self.collection_plan.get("information_needs", {}).get(
            "required_information", []
        )

        info_by_id = {item.get("id"): item for item in required_info}

        for result in self.collection_results:
            if result.get("status") != "collected":
                continue

            info_id = result.get("info_id")
            plan_item = info_by_id.get(info_id)

            if plan_item:
                category = plan_item.get("category", "codebase")
                if category in organized:
                    organized[category][info_id] = result.get("collected_data")

        return organized

    def _extract_understanding_summary(self) -> dict[str, Any]:
        """理解結果のサマリーを抽出する.

        Returns:
            理解結果のサマリー

        """
        if not self.understanding_result:
            return {
                "task_type": "unknown",
                "primary_goal": "不明",
                "understanding_confidence": 0.0,
            }

        request_understanding = self.understanding_result.get(
            "request_understanding", {}
        )

        return {
            "task_type": request_understanding.get("task_type", "unknown"),
            "primary_goal": request_understanding.get("primary_goal", "不明"),
            "expected_deliverables": request_understanding.get(
                "expected_deliverables", []
            ),
            "constraints": request_understanding.get("constraints", []),
            "scope": request_understanding.get("scope", {}),
            "understanding_confidence": request_understanding.get(
                "understanding_confidence", 0.0
            ),
            "ambiguities": request_understanding.get("ambiguities", []),
        }

    def _generate_recommendations(self) -> list[str]:
        """計画への推奨事項を生成する.

        Returns:
            推奨事項のリスト

        """
        recommendations = []

        # 情報ギャップに基づく推奨
        if self.information_gaps:
            recommendations.append(
                f"情報ギャップが{len(self.information_gaps)}件あります。"
                "計画時に代替アプローチを検討してください。"
            )

        # 推測に基づく推奨
        if self.assumptions:
            recommendations.append(
                f"{len(self.assumptions)}件の情報を推測しました。"
                "実行時に確認が必要な場合があります。"
            )

        # 理解の確信度に基づく推奨
        understanding_confidence = self._extract_understanding_summary().get(
            "understanding_confidence", 0.0
        )
        confidence_threshold = self.understanding_config.get(
            "confidence_threshold", 0.7
        )

        if understanding_confidence < confidence_threshold:
            recommendations.append(
                f"理解の確信度が{understanding_confidence:.0%}と低めです。"
                "計画は慎重に立ててください。"
            )

        return recommendations

    # 通知メソッド

    def _post_start_notification(self) -> None:
        """開始通知を投稿する."""
        if self.progress_manager:
            self.progress_manager.add_history_entry(
                entry_type="phase",
                title="🔍 Pre Planning Phase - ▶️ Started",
                details="タスク内容を理解し、計画に必要な情報を収集しています...",
            )

    def _post_understanding_complete_notification(self) -> None:
        """理解完了通知を投稿する."""
        if not self.understanding_result or not self.progress_manager:
            return

        request_understanding = self.understanding_result.get(
            "request_understanding", {}
        )

        task_type = request_understanding.get("task_type", "不明")
        primary_goal = request_understanding.get("primary_goal", "不明")
        deliverables = request_understanding.get("expected_deliverables", [])
        scope = request_understanding.get("scope", {})
        confidence = request_understanding.get("understanding_confidence", 0.0)

        deliverables_str = (
            "\n".join(f"- {d}" for d in deliverables) if deliverables else "- なし"
        )
        in_scope = scope.get("in_scope", [])
        out_of_scope = scope.get("out_of_scope", [])
        in_scope_str = ", ".join(in_scope) if in_scope else "全体"
        out_scope_str = ", ".join(out_of_scope) if out_of_scope else "なし"

        details = f"""**タスク種別**: {task_type}

**主な目標**:
{primary_goal}

**期待される成果物**:
{deliverables_str}

**スコープ**:
- 対象: {in_scope_str}
- 対象外: {out_scope_str}

*理解の確信度: {confidence:.0%}*"""

        self.progress_manager.add_history_entry(
            entry_type="phase",
            title="📋 Request Understanding - ✅ Completed",
            details=details,
        )

    def _post_collection_complete_notification(self) -> None:
        """収集完了通知を投稿する."""
        if not self.progress_manager:
            return

        # 収集結果をまとめる
        collected_items = []
        assumed_items = []

        for result in self.collection_results:
            info_id = result.get("info_id", "unknown")
            status = result.get("status", "unknown")

            if status == "collected":
                collected_items.append(f"✅ {info_id}")
            elif status == "failed":
                # 推測されたかチェック
                was_assumed = any(
                    a.get("info_id") == info_id for a in self.assumptions
                )
                if was_assumed:
                    assumed_items.append(f"⚠️ {info_id} (推測)")
                else:
                    assumed_items.append(f"❌ {info_id} (収集失敗)")

        collected_str = (
            "\n".join(collected_items) if collected_items else "なし"
        )
        assumed_str = "\n".join(assumed_items) if assumed_items else ""

        assumptions_section = ""
        if self.assumptions:
            assumption_details = []
            for assumption in self.assumptions:
                info_id = assumption.get("info_id", "unknown")
                value = assumption.get("assumed_value", "")[:TEXT_TRUNCATION_LIMIT]
                reasoning = assumption.get("reasoning", "")[:TEXT_TRUNCATION_LIMIT]
                assumption_details.append(f"- {info_id}: {value} (理由: {reasoning})")

            assumptions_section = f"""

**推測事項**:
以下の情報は収集できなかったため、推測で補完しました：
{chr(10).join(assumption_details)}"""

        details = f"""**収集完了**: {len(collected_items)}件
**推測適用**: {len(assumed_items)}件

{collected_str}
{assumed_str}{assumptions_section}

計画フェーズに移行します..."""

        self.progress_manager.add_history_entry(
            entry_type="phase",
            title="📦 Information Collection - ✅ Completed",
            details=details,
        )

    def _post_assumption_notification(self, assumption: dict[str, Any]) -> None:
        """推測通知を投稿する.

        Args:
            assumption: 推測結果

        """
        if not self.progress_manager:
            return

        info_id = assumption.get("info_id", "unknown")
        value = assumption.get("assumed_value", "")
        reasoning = assumption.get("reasoning", "")
        confidence = assumption.get("confidence", 0.0)

        details = f"""**項目**: {info_id}
**推測値**: {value}
**理由**: {reasoning}
**確信度**: {confidence:.0%}"""

        self.progress_manager.add_history_entry(
            entry_type="assumption",
            title="⚠️ Information Assumed",
            details=details,
        )

