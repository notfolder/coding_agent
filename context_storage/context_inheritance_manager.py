"""コンテキスト引き継ぎマネージャーモジュール.

同一Issue/MR/PRの過去コンテキストを検索し、引き継ぎを管理するクラスを提供します。
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from handlers.task_key import TaskKey


@dataclass
class PreviousContext:
    """過去のコンテキスト情報を表すデータクラス.

    Attributes:
        uuid: タスクのUUID
        task_key_dict: TaskKeyの辞書表現
        status: タスクのステータス（completed, stopped等）
        completed_at: タスク完了日時
        final_summary: 最終要約テキスト
        metadata: 過去の処理設定情報
        planning_history: Planning Mode時の計画履歴（オプション）

    """

    uuid: str
    task_key_dict: dict[str, Any]
    status: str
    completed_at: datetime | None
    final_summary: str | None
    metadata: dict[str, Any] = field(default_factory=dict)
    planning_history: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class InheritanceContext:
    """引き継ぎコンテキスト情報を表すデータクラス.

    Attributes:
        previous_context: 過去のコンテキスト情報
        final_summary: 引き継ぎ用の最終要約テキスト
        planning_summary: Planning Mode用の計画サマリー（オプション）

    """

    previous_context: PreviousContext
    final_summary: str
    planning_summary: dict[str, Any] | None = None


class ContextInheritanceManager:
    """コンテキスト引き継ぎマネージャー.

    同一Issue/MR/PRの過去コンテキストを検索し、引き継ぎを管理します。
    """

    # デフォルト設定値
    DEFAULT_EXPIRY_DAYS = 90
    DEFAULT_MAX_TOKENS = 8000
    MAX_DB_RETRIES = 3

    def __init__(self, base_dir: Path, config: dict[str, Any]) -> None:
        """ContextInheritanceManagerを初期化する.

        Args:
            base_dir: コンテキストストレージのベースディレクトリ
            config: アプリケーション設定辞書

        """
        self.base_dir = base_dir
        self.config = config
        self.logger = logging.getLogger(__name__)

        # context_inheritance設定を取得
        inheritance_config = config.get("context_inheritance", {})
        self.enabled = inheritance_config.get("enabled", True)
        self.expiry_days = inheritance_config.get(
            "context_expiry_days", self.DEFAULT_EXPIRY_DAYS,
        )
        self.max_inherited_tokens = inheritance_config.get(
            "max_inherited_tokens", self.DEFAULT_MAX_TOKENS,
        )

        # Planning Mode設定
        planning_config = inheritance_config.get("planning", {})
        self.inherit_plans = planning_config.get("inherit_plans", True)
        self.inherit_verifications = planning_config.get("inherit_verifications", True)
        self.inherit_reflections = planning_config.get("inherit_reflections", True)
        self.max_previous_plans = planning_config.get("max_previous_plans", 3)
        self.reuse_successful_patterns = planning_config.get(
            "reuse_successful_patterns", True,
        )

        # データベースパス
        self.db_path = base_dir / "tasks.db"
        self.completed_dir = base_dir / "completed"

    def find_previous_contexts(
        self, task_key: TaskKey,
    ) -> list[PreviousContext]:
        """同一TaskKeyを持つ過去のコンテキストを検索する.

        Args:
            task_key: 検索対象のTaskKey

        Returns:
            過去のコンテキストのリスト（完了日時の降順）

        """
        if not self.enabled:
            return []

        if not self.db_path.exists():
            self.logger.debug("タスクデータベースが存在しません: %s", self.db_path)
            return []

        # TaskKeyから検索条件を取得
        task_dict = task_key.to_dict()
        task_type = task_dict.get("type", "")

        # task_typeからtask_sourceとtask_typeを分離
        # 例: github_issue -> github, issue
        # 例: github_pull_request -> github, pull_request
        if "_" in task_type:
            parts = task_type.split("_", 1)
            task_source = parts[0]
            actual_task_type = parts[1] if len(parts) > 1 else task_type
        else:
            task_source = task_type
            actual_task_type = task_type

        # GitHubの場合
        owner = task_dict.get("owner", "")
        repo = task_dict.get("repo", "")
        task_id = str(task_dict.get("number", ""))

        # GitLabの場合
        if not owner and not repo:
            # GitLab形式: project_id, issue_iid or mr_iid
            project_id = task_dict.get("project_id", "")
            if project_id:
                owner = ""  # GitLabはownerなし
                repo = str(project_id)
            task_id = str(
                task_dict.get("issue_iid", "") or task_dict.get("mr_iid", ""),
            )

        # 有効期限の計算
        expiry_date = datetime.now(timezone.utc) - timedelta(days=self.expiry_days)

        # データベースから検索
        previous_contexts = []
        for retry in range(self.MAX_DB_RETRIES):
            try:
                with sqlite3.connect(self.db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    cursor = conn.cursor()

                    # 検索クエリを実行
                    # statusがcompletedまたはstoppedで、有効期限内のものを検索
                    cursor.execute(
                        """
                        SELECT uuid, task_source, owner, repo, task_type, task_id,
                               status, completed_at, user
                        FROM tasks
                        WHERE task_source = ?
                          AND owner = ?
                          AND repo = ?
                          AND task_type = ?
                          AND task_id = ?
                          AND status IN ('completed', 'stopped')
                          AND completed_at >= ?
                        ORDER BY completed_at DESC
                        """,
                        (
                            task_source,
                            owner,
                            repo,
                            actual_task_type,
                            task_id,
                            expiry_date.isoformat(),
                        ),
                    )

                    rows = cursor.fetchall()

                    for row in rows:
                        # 過去コンテキストを構築
                        context = self._build_previous_context(dict(row))
                        if context:
                            previous_contexts.append(context)

                    self.logger.debug(
                        "過去コンテキストを %d 件検出しました", len(previous_contexts),
                    )
                    break  # 成功したらループを抜ける

            except sqlite3.Error as e:
                self.logger.warning(
                    "データベースエラー (リトライ %d/%d): %s",
                    retry + 1,
                    self.MAX_DB_RETRIES,
                    e,
                )
                if retry == self.MAX_DB_RETRIES - 1:
                    self.logger.error("データベース接続に失敗しました")
                    return []
                # 指数バックオフで待機
                import time
                wait_time = 0.1 * (2 ** retry)  # 0.1秒、0.2秒、0.4秒
                time.sleep(wait_time)

        return previous_contexts

    def get_inheritance_context(
        self, task_key: TaskKey,
    ) -> InheritanceContext | None:
        """引き継ぎ用のコンテキストを取得する.

        同一TaskKeyを持つ過去のコンテキストから、最新の1件の最終要約を取得します。

        Args:
            task_key: 検索対象のTaskKey

        Returns:
            引き継ぎコンテキスト、または引き継ぎ対象がない場合はNone

        """
        if not self.enabled:
            return None

        # 過去コンテキストを検索
        previous_contexts = self.find_previous_contexts(task_key)

        if not previous_contexts:
            self.logger.info("引き継ぎ対象の過去コンテキストが見つかりません")
            return None

        # 最新の1件を使用
        previous_context = previous_contexts[0]

        # 最終要約が存在するか確認
        if not previous_context.final_summary:
            self.logger.info(
                "過去コンテキスト %s に最終要約がありません",
                previous_context.uuid[:8],
            )
            return None

        # Planning Modeサマリーを生成（有効な場合）
        planning_summary = None
        if self.inherit_plans and previous_context.planning_history:
            planning_summary = self._build_planning_summary(
                previous_context.planning_history,
            )

        # トークン制限をチェック
        final_summary = self._truncate_summary_if_needed(
            previous_context.final_summary,
        )

        self.logger.info(
            "引き継ぎコンテキストを取得しました: uuid=%s, completed_at=%s",
            previous_context.uuid[:8],
            previous_context.completed_at,
        )

        return InheritanceContext(
            previous_context=previous_context,
            final_summary=final_summary,
            planning_summary=planning_summary,
        )

    def create_initial_context(
        self,
        inheritance_context: InheritanceContext,
        user_request: str,
    ) -> list[dict[str, Any]]:
        """引き継ぎ情報を含む初期コンテキストを生成する.

        仕様書に従い、以下の順序でメッセージを構築します：
        1. 前回の最終要約（assistantロール、プレフィックス付き）
        2. 今回のユーザー依頼（userロール）

        Args:
            inheritance_context: 引き継ぎコンテキスト
            user_request: 今回のユーザー依頼（Issue/MR/PRの内容）

        Returns:
            初期コンテキストのメッセージリスト

        """
        messages = []

        # 前回の最終要約をassistantロールで追加（プレフィックス付き）
        summary_with_prefix = self._format_summary_with_prefix(
            inheritance_context.final_summary,
            inheritance_context.previous_context,
            inheritance_context.planning_summary,
        )
        messages.append({
            "role": "assistant",
            "content": summary_with_prefix,
        })

        # 今回のユーザー依頼をuserロールで追加
        messages.append({
            "role": "user",
            "content": user_request,
        })

        return messages

    def generate_notification_comment(
        self, inheritance_context: InheritanceContext,
    ) -> str:
        """引き継ぎ通知コメントを生成する.

        Args:
            inheritance_context: 引き継ぎコンテキスト

        Returns:
            通知コメントの文字列

        """
        prev = inheritance_context.previous_context
        completed_at_str = (
            prev.completed_at.strftime("%Y-%m-%d %H:%M:%S")
            if prev.completed_at
            else "不明"
        )

        comment_lines = [
            "📋 **過去のコンテキストを引き継ぎました**",
            "",
            f"- 引き継ぎ元: #{prev.uuid[:8]}",
            f"- 前回処理日時: {completed_at_str}",
            "- 引き継ぎ内容: 最終要約",
            "",
            "過去の処理内容を考慮して、現在の要求に対応します。",
        ]

        return "\n".join(comment_lines)

    def _build_previous_context(
        self, row: dict[str, Any],
    ) -> PreviousContext | None:
        """データベース行から過去コンテキストを構築する.

        Args:
            row: データベースの行データ

        Returns:
            過去コンテキスト、または構築失敗時はNone

        """
        uuid = row.get("uuid", "")
        if not uuid:
            return None

        # 完了日時をパース
        completed_at = None
        completed_at_str = row.get("completed_at")
        if completed_at_str:
            try:
                # ISO形式の日時をパース
                completed_at = datetime.fromisoformat(
                    completed_at_str.replace("Z", "+00:00"),
                )
            except ValueError:
                self.logger.warning(
                    "日時のパースに失敗: %s", completed_at_str,
                )

        # コンテキストディレクトリから最終要約を取得
        final_summary = self._load_final_summary(uuid)

        # メタデータを読み込み
        metadata = self._load_metadata(uuid)

        # Planning履歴を読み込み（有効な場合）
        planning_history = []
        if self.inherit_plans:
            planning_history = self._load_planning_history(uuid)

        # TaskKey辞書を構築
        task_key_dict = {
            "task_source": row.get("task_source", ""),
            "owner": row.get("owner", ""),
            "repo": row.get("repo", ""),
            "task_type": row.get("task_type", ""),
            "task_id": row.get("task_id", ""),
        }

        return PreviousContext(
            uuid=uuid,
            task_key_dict=task_key_dict,
            status=row.get("status", ""),
            completed_at=completed_at,
            final_summary=final_summary,
            metadata=metadata,
            planning_history=planning_history,
        )

    def _load_final_summary(self, uuid: str) -> str | None:
        """最終要約をsummaries.jsonlから読み込む.

        Args:
            uuid: タスクのUUID

        Returns:
            最終要約テキスト、または読み込み失敗時はNone

        """
        context_dir = self.completed_dir / uuid
        summaries_file = context_dir / "summaries.jsonl"

        if not summaries_file.exists():
            self.logger.debug("summaries.jsonlが見つかりません: %s", summaries_file)
            return None

        try:
            # 最新の要約を取得（ファイルの最後の行）
            latest_summary = None
            with summaries_file.open() as f:
                for line in f:
                    if line.strip():
                        summary_entry = json.loads(line)
                        latest_summary = summary_entry.get("summary")

            return latest_summary

        except (json.JSONDecodeError, OSError) as e:
            self.logger.warning("summaries.jsonlの読み込みに失敗: %s", e)
            return None

    def _load_metadata(self, uuid: str) -> dict[str, Any]:
        """メタデータをmetadata.jsonから読み込む.

        Args:
            uuid: タスクのUUID

        Returns:
            メタデータ辞書

        """
        context_dir = self.completed_dir / uuid
        metadata_file = context_dir / "metadata.json"

        if not metadata_file.exists():
            return {}

        try:
            with metadata_file.open() as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            self.logger.warning("metadata.jsonの読み込みに失敗: %s", e)
            return {}

    def _load_planning_history(self, uuid: str) -> list[dict[str, Any]]:
        """Planning履歴をplanning/{uuid}.jsonlから読み込む.

        Args:
            uuid: タスクのUUID

        Returns:
            Planning履歴のリスト

        """
        context_dir = self.completed_dir / uuid
        planning_dir = context_dir / "planning"
        planning_file = planning_dir / f"{uuid}.jsonl"

        if not planning_file.exists():
            return []

        try:
            entries = []
            with planning_file.open() as f:
                for line in f:
                    if line.strip():
                        entries.append(json.loads(line))

            # 最大件数に制限
            if len(entries) > self.max_previous_plans:
                # 最新のエントリを優先
                entries = entries[-self.max_previous_plans:]

            return entries

        except (json.JSONDecodeError, OSError) as e:
            self.logger.warning("planning履歴の読み込みに失敗: %s", e)
            return []

    def _build_planning_summary(
        self, planning_history: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Planning Mode用のサマリーを構築する.

        Args:
            planning_history: Planning履歴のリスト

        Returns:
            Planning Modeサマリー辞書

        """
        summary: dict[str, Any] = {
            "previous_plan_summary": {},
            "execution_history": {
                "successful_actions": [],
                "failed_actions": [],
                "key_failures": [],
            },
            "verification_history": {
                "verification_rounds": 0,
                "issues_found": [],
                "issues_resolved": [],
            },
            "recommendations": [],
        }

        for entry in planning_history:
            entry_type = entry.get("type", "")

            if entry_type == "plan":
                plan = entry.get("plan", {})
                summary["previous_plan_summary"] = {
                    "goal": plan.get("goal_understanding", {}).get(
                        "goal_summary", "",
                    ),
                    "subtasks": [
                        t.get("task_id", "")
                        for t in plan.get("task_decomposition", {}).get(
                            "subtasks", [],
                        )
                    ],
                    "completion_status": "completed",
                }

            elif entry_type == "verification" and self.inherit_verifications:
                verification = entry.get("verification_result", {})
                summary["verification_history"]["verification_rounds"] += 1
                issues = verification.get("issues_found", [])
                summary["verification_history"]["issues_found"].extend(issues)
                if verification.get("verification_passed"):
                    summary["verification_history"]["issues_resolved"].extend(
                        issues,
                    )

            elif entry_type == "reflection" and self.inherit_reflections:
                evaluation = entry.get("evaluation", {})
                if evaluation.get("success"):
                    summary["execution_history"]["successful_actions"].append(
                        evaluation.get("action_summary", ""),
                    )
                else:
                    summary["execution_history"]["failed_actions"].append(
                        evaluation.get("action_summary", ""),
                    )
                    failure_reason = evaluation.get("failure_reason")
                    if failure_reason:
                        summary["execution_history"]["key_failures"].append(
                            failure_reason,
                        )

        # 成功パターンから推奨事項を生成
        if self.reuse_successful_patterns:
            successful = summary["execution_history"]["successful_actions"]
            if successful:
                summary["recommendations"].append(
                    f"過去に成功したアクション: {', '.join(successful[:3])}",
                )

            failed = summary["execution_history"]["key_failures"]
            if failed:
                summary["recommendations"].append(
                    f"過去に失敗したアクション（回避推奨）: {', '.join(failed[:3])}",
                )

        return summary

    def _truncate_summary_if_needed(self, summary: str) -> str:
        """必要に応じて要約をトークン制限内に切り詰める.

        Args:
            summary: 元の要約テキスト

        Returns:
            トークン制限内に収まる要約テキスト

        """
        # 簡易的なトークン数推定（1トークン≒4文字）
        estimated_tokens = len(summary) // 4

        if estimated_tokens <= self.max_inherited_tokens:
            return summary

        # トークン制限を超える場合は切り詰め
        max_chars = self.max_inherited_tokens * 4
        truncated = summary[: max_chars - 50]  # 余裕を持たせる
        truncated += "\n\n... (要約が長いため一部省略されました)"

        self.logger.info(
            "要約をトークン制限内に切り詰めました: %d -> %d 文字",
            len(summary),
            len(truncated),
        )

        return truncated

    def _format_summary_with_prefix(
        self,
        final_summary: str,
        previous_context: PreviousContext,
        planning_summary: dict[str, Any] | None = None,
    ) -> str:
        """要約にプレフィックスを付けてフォーマットする.

        仕様書に従い、「前回の処理要約:」プレフィックスを付けて
        引き継ぎ情報であることを明示します。

        Args:
            final_summary: 最終要約テキスト
            previous_context: 過去のコンテキスト情報
            planning_summary: Planning Modeサマリー（オプション）

        Returns:
            フォーマットされた要約テキスト

        """
        completed_at_str = (
            previous_context.completed_at.strftime("%Y-%m-%d %H:%M:%S")
            if previous_context.completed_at
            else "不明"
        )

        lines = [
            "前回の処理要約:",
            f"(引き継ぎ元: {previous_context.uuid[:8]}, 処理日時: {completed_at_str})",
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
                status = plan_summary.get("completion_status", "")
                if status:
                    lines.append(f"Completion Status: {status}")

            exec_history = planning_summary.get("execution_history", {})
            if exec_history:
                lines.append("")
                lines.append("=== Execution History ===")
                successful = exec_history.get("successful_actions", [])
                if successful:
                    lines.append(f"Successful Actions: {len(successful)} items")
                failed = exec_history.get("failed_actions", [])
                if failed:
                    lines.append(f"Failed Actions: {len(failed)} items")
                key_failures = exec_history.get("key_failures", [])
                if key_failures:
                    lines.append(f"Key Failures: {', '.join(key_failures[:3])}")

            verification = planning_summary.get("verification_history", {})
            if verification and verification.get("verification_rounds", 0) > 0:
                lines.append("")
                lines.append("=== Verification History ===")
                lines.append(
                    f"Verification Rounds: {verification.get('verification_rounds', 0)}",
                )
                issues_found = verification.get("issues_found", [])
                if issues_found:
                    lines.append(f"Issues Found: {len(issues_found)}")
                issues_resolved = verification.get("issues_resolved", [])
                if issues_resolved:
                    lines.append(f"Issues Resolved: {len(issues_resolved)}")

            recommendations = planning_summary.get("recommendations", [])
            if recommendations:
                lines.append("")
                lines.append("=== Recommendations for Current Processing ===")
                for rec in recommendations:
                    lines.append(f"- {rec}")

        return "\n".join(lines)
