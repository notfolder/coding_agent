"""新規コメント検知とコンテキスト反映機能.

このモジュールは、Issue/MRの処理中に新しいユーザーコメントを検出し、
LLMコンテキストに反映する機能を提供します。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from handlers.task import Task


class CommentDetectionManager:
    """Issue/MRの新規コメント検出を管理するクラス.

    処理中に追加された新規ユーザーコメントを検出し、
    LLMコンテキストに追加する機能を提供します。
    """

    def __init__(self, task: Task, config: dict[str, Any]) -> None:
        """CommentDetectionManagerを初期化する.

        Args:
            task: 処理対象のタスクオブジェクト
            config: アプリケーション設定辞書

        """
        self.task = task
        self.config = config
        self.logger = logging.getLogger(__name__)

        # コメント検出機能の有効/無効フラグ
        self.enabled = False

        # 前回までのコメントIDセット（文字列として管理）
        self.last_comment_ids: set[str] = set()

        # 前回チェック時刻
        self.last_check_time: datetime | None = None

        # bot自身のユーザー名（除外用）
        self.bot_username: str | None = None

        # 有効/無効とbot_usernameの決定
        self._configure()

    def _configure(self) -> None:
        """設定からbot_usernameを取得し、機能の有効/無効を決定する."""
        import os

        # タスクタイプを取得
        task_key = self.task.get_task_key().to_dict()
        task_type = task_key.get("type", "")

        if task_type.startswith("github"):
            # GitHub: 環境変数 > 設定ファイル
            self.bot_username = os.environ.get(
                "GITHUB_BOT_NAME",
                self.config.get("github", {}).get("bot_name"),
            )
        elif task_type.startswith("gitlab"):
            # GitLab: 環境変数 > 設定ファイル
            self.bot_username = os.environ.get(
                "GITLAB_BOT_NAME",
                self.config.get("gitlab", {}).get("bot_name"),
            )
        else:
            self.logger.warning("不明なタスクタイプ: %s", task_type)
            self.bot_username = None

        # bot_usernameが取得できない場合は機能を無効化
        if not self.bot_username:
            self.logger.warning("bot_usernameが設定されていません。コメント検出機能を無効化します。")
            self.enabled = False
        else:
            self.enabled = True
            self.logger.info(
                "コメント検出機能を有効化しました (bot_username=%s)",
                self.bot_username,
            )

    def initialize(self) -> None:
        """現在のコメント一覧を取得してlast_comment_idsを初期化する.

        タスク開始時に呼び出して、既存のコメントをすべて記録します。
        """
        if not self.enabled:
            self.logger.debug("コメント検出機能が無効のため、初期化をスキップします")
            return

        try:
            # 現在のコメント一覧を取得
            comments = self.task.get_comments()

            # コメントIDをセットに追加（文字列として管理）
            self.last_comment_ids = {
                str(comment.get("id", "")) for comment in comments if comment.get("id") is not None
            }

            # チェック時刻を記録
            self.last_check_time = datetime.now(timezone.utc)

            self.logger.info(
                "コメント検出を初期化しました: %d件のコメントを記録",
                len(self.last_comment_ids),
            )
        except Exception as e:
            self.logger.warning("コメント取得中にエラー発生: %s", e)
            # エラーでも処理を継続

    def check_for_new_comments(self) -> list[dict[str, Any]]:
        """新規コメントを検出する.

        Returns:
            新規コメントのリスト（空リストの場合は新規なし）

        """
        if not self.enabled:
            return []

        try:
            # 現在のコメント一覧を取得
            current_comments = self.task.get_comments()

            # 新規コメントを抽出
            new_comments = []
            current_ids = set()

            for comment in current_comments:
                comment_id_raw = comment.get("id")
                if comment_id_raw is None:
                    continue
                comment_id = str(comment_id_raw)

                current_ids.add(comment_id)

                # 新規コメントの判定
                if comment_id not in self.last_comment_ids:
                    # bot自身のコメントを除外
                    if not self.is_bot_comment(comment):
                        new_comments.append(comment)
                    else:
                        self.logger.debug(
                            "bot自身のコメントを除外しました: id=%s",
                            comment_id,
                        )

            # 状態を更新
            self.last_comment_ids = current_ids
            self.last_check_time = datetime.now(timezone.utc)

            if new_comments:
                self.logger.info(
                    "新規コメントを検出しました: %d件 (Task: %s)",
                    len(new_comments),
                    getattr(self.task, "uuid", "unknown"),
                )
            else:
                self.logger.debug(
                    "新規コメントなし (Task: %s)",
                    getattr(self.task, "uuid", "unknown"),
                )

            return new_comments

        except Exception as e:
            self.logger.warning(
                "コメント取得中にエラー発生: %s (Task: %s)",
                e,
                getattr(self.task, "uuid", "unknown"),
            )
            # エラー時は空リストを返して処理を継続
            return []

    def is_bot_comment(self, comment: dict[str, Any]) -> bool:
        """コメントがbot自身によるものか判定する.

        Args:
            comment: コメント情報の辞書

        Returns:
            botのコメントの場合True

        """
        if not self.bot_username:
            return False

        author = comment.get("author", "")
        return author == self.bot_username

    def format_comment_message(self, comments: list[dict[str, Any]]) -> str:
        """検出したコメントをLLMメッセージ形式に整形する.

        Args:
            comments: コメントリスト

        Returns:
            整形されたメッセージ文字列

        """
        if not comments:
            return ""

        if len(comments) == 1:
            # 単一コメントの場合
            comment = comments[0]
            author = comment.get("author", "unknown")
            body = comment.get("body", "")
            return f"[New Comment from @{author}]:\n{body}"

        # 複数コメントの場合
        lines = ["[New Comments Detected]:", ""]

        for i, comment in enumerate(comments, 1):
            author = comment.get("author", "unknown")
            body = comment.get("body", "")
            timestamp = comment.get("created_at", "")

            lines.append(f"Comment {i} from @{author} ({timestamp}):")
            lines.append(body)
            lines.append("")

        return "\n".join(lines)

    def add_to_context(
        self,
        llm_client: Any,  # noqa: ANN401
        comments: list[dict[str, Any]],
    ) -> None:
        """検出したコメントをLLMコンテキストに追加する.

        Args:
            llm_client: LLMクライアントインスタンス
            comments: 追加するコメントのリスト

        """
        if not comments:
            return

        try:
            # メッセージを整形
            message = self.format_comment_message(comments)

            # LLMコンテキストに追加
            llm_client.send_user_message(message)

            self.logger.info(
                "新規コメントをコンテキストに追加しました: %d件 (Task: %s)",
                len(comments),
                getattr(self.task, "uuid", "unknown"),
            )
        except Exception as e:
            self.logger.warning(
                "コンテキスト追加中にエラー発生: %s (Task: %s)",
                e,
                getattr(self.task, "uuid", "unknown"),
            )

    def get_state(self) -> dict[str, Any]:
        """一時停止時の状態永続化用に現在の状態を取得する.

        Returns:
            状態辞書

        """
        return {
            "last_comment_ids": list(self.last_comment_ids),
            "last_check_timestamp": (self.last_check_time.isoformat() if self.last_check_time else None),
        }

    def restore_state(self, state: dict[str, Any]) -> None:
        """再開時の状態復元用.

        Args:
            state: get_state()と同じ構造の状態辞書

        """
        if not state:
            self.logger.debug("復元する状態がありません")
            return

        try:
            # last_comment_idsを復元
            comment_ids = state.get("last_comment_ids", [])
            self.last_comment_ids = set(comment_ids)

            # last_check_timeを復元
            timestamp = state.get("last_check_timestamp")
            if timestamp:
                self.last_check_time = datetime.fromisoformat(timestamp)

            self.logger.info(
                "コメント検出状態を復元しました: %d件のコメントID",
                len(self.last_comment_ids),
            )
        except Exception as e:
            self.logger.warning(
                "コメント検出状態の復元に失敗しました: %s。新規初期化を実行します。",
                e,
            )
            # 復元失敗時は新規初期化
            self.initialize()
