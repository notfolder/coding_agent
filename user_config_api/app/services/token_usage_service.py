"""トークン使用量サービス.

ユーザー毎のトークン使用量を集計・取得するサービスを提供します。
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class TokenUsageService:
    """トークン使用量サービス.

    tasks.dbからユーザー毎のトークン使用量を集計・取得します。
    """

    # 全ユーザー取得時の上限数
    MAX_USERS_LIMIT = 20

    def __init__(self, tasks_db_path: str | Path | None = None) -> None:
        """TokenUsageServiceを初期化する.

        Args:
            tasks_db_path: tasks.dbのパス (Noneの場合は自動検出)

        """
        self.tasks_db_path = self._resolve_db_path(tasks_db_path)

    def _resolve_db_path(self, tasks_db_path: str | Path | None) -> Path:
        """tasks.dbのパスを解決する.

        Args:
            tasks_db_path: 指定されたパス (Noneの場合は自動検出)

        Returns:
            tasks.dbのパス

        """
        if tasks_db_path is not None:
            return Path(tasks_db_path)

        # 自動検出のパス候補
        candidates = [
            Path("/app/contexts/tasks.db"),  # Dockerコンテナ内
            Path("contexts/tasks.db"),  # 通常の実行
            Path(__file__).parent.parent.parent.parent / "contexts" / "tasks.db",
        ]

        for path in candidates:
            if path.exists():
                return path

        # 見つからない場合はデフォルトパスを返す (存在チェックは呼び出し側で行う)
        return Path("contexts/tasks.db")

    def _get_connection(self) -> sqlite3.Connection:
        """データベース接続を取得する.

        Returns:
            SQLite接続オブジェクト

        Raises:
            FileNotFoundError: データベースファイルが存在しない場合

        """
        if not self.tasks_db_path.exists():
            raise FileNotFoundError(f"tasks.db not found: {self.tasks_db_path}")

        # 読み取り専用モードで接続 (URIモード使用)
        conn = sqlite3.connect(
            f"file:{self.tasks_db_path}?mode=ro",
            uri=True,
            timeout=10.0,
        )
        conn.row_factory = sqlite3.Row
        return conn

    def _get_now(self) -> datetime:
        """現在時刻を取得する (ローカルタイムゾーン).

        Returns:
            現在時刻

        """
        # UTC時刻を取得してローカルタイムに変換
        return datetime.now(tz=timezone.utc).astimezone()

    def get_user_token_usage(self, username: str) -> dict[str, Any]:
        """指定ユーザーの期間別トークン使用量を取得する.

        Args:
            username: ユーザー名

        Returns:
            今日・今週・今月のトークン使用量を含む辞書
            {
                "username": str,
                "today": int,
                "this_week": int,
                "this_month": int,
                "last_updated": str (ISO 8601形式)
            }

        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # 日付の基準を計算
                now = self._get_now()
                today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

                # 週の開始 (月曜日を週の開始とする)
                week_start = today_start - timedelta(days=today_start.weekday())

                # 月の開始
                month_start = today_start.replace(day=1)

                # 各期間のトークン合計を取得
                today_tokens = self._get_tokens_since(
                    cursor, username, today_start.isoformat(),
                )
                week_tokens = self._get_tokens_since(
                    cursor, username, week_start.isoformat(),
                )
                month_tokens = self._get_tokens_since(
                    cursor, username, month_start.isoformat(),
                )

                return {
                    "username": username,
                    "today": today_tokens,
                    "this_week": week_tokens,
                    "this_month": month_tokens,
                    "last_updated": now.isoformat(),
                }

        except FileNotFoundError:
            logger.warning("tasks.db not found, returning zero usage")
            return {
                "username": username,
                "today": 0,
                "this_week": 0,
                "this_month": 0,
                "last_updated": self._get_now().isoformat(),
            }
        except sqlite3.Error:
            logger.exception("Database error while getting token usage")
            return {
                "username": username,
                "today": 0,
                "this_week": 0,
                "this_month": 0,
                "last_updated": self._get_now().isoformat(),
            }

    def _get_tokens_since(
        self,
        cursor: sqlite3.Cursor,
        username: str,
        since: str,
    ) -> int:
        """指定日時以降のトークン数を取得する.

        Args:
            cursor: SQLiteカーソル
            username: ユーザー名
            since: 開始日時 (ISO 8601形式)

        Returns:
            トークン数 (負の値は0として扱う)

        """
        cursor.execute(
            """
            SELECT COALESCE(SUM(total_tokens), 0) as total
            FROM tasks
            WHERE user = ? AND created_at >= ?
            """,
            (username, since),
        )
        result = cursor.fetchone()
        total = result["total"] if result else 0
        # 負の値は0として扱う
        return max(0, total)

    def get_user_daily_history(
        self,
        username: str,
        days: int = 30,
    ) -> dict[str, Any]:
        """指定ユーザーの日別トークン使用履歴を取得する.

        Args:
            username: ユーザー名
            days: 取得日数 (デフォルト30日)

        Returns:
            日付とトークン数のリストを含む辞書
            {
                "username": str,
                "history": [{"date": str, "tokens": int}, ...],
                "period_start": str,
                "period_end": str
            }

        """
        # daysの範囲制限 (1-365日)
        days = max(1, min(365, days))

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                now = self._get_now()
                end_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
                start_date = end_date - timedelta(days=days - 1)

                # 日別の集計クエリ
                cursor.execute(
                    """
                    SELECT DATE(created_at) as date, SUM(total_tokens) as tokens
                    FROM tasks
                    WHERE user = ? AND DATE(created_at) >= DATE(?)
                    GROUP BY DATE(created_at)
                    ORDER BY date
                    """,
                    (username, start_date.isoformat()),
                )

                # 結果を辞書に変換
                db_results = {
                    row["date"]: max(0, row["tokens"]) for row in cursor.fetchall()
                }

                # 欠損日を0で補完
                history = []
                current_date = start_date
                while current_date <= end_date:
                    date_str = current_date.strftime("%Y-%m-%d")
                    tokens = db_results.get(date_str, 0)
                    history.append({"date": date_str, "tokens": tokens})
                    current_date += timedelta(days=1)

                return {
                    "username": username,
                    "history": history,
                    "period_start": start_date.strftime("%Y-%m-%d"),
                    "period_end": end_date.strftime("%Y-%m-%d"),
                }

        except FileNotFoundError:
            logger.warning("tasks.db not found, returning empty history")
            return self._empty_history(username, days)
        except sqlite3.Error:
            logger.exception("Database error while getting daily history")
            return self._empty_history(username, days)

    def _empty_history(self, username: str, days: int) -> dict[str, Any]:
        """空の履歴データを生成する.

        Args:
            username: ユーザー名
            days: 日数

        Returns:
            0埋めされた履歴データ

        """
        now = self._get_now()
        end_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start_date = end_date - timedelta(days=days - 1)

        history = []
        current_date = start_date
        while current_date <= end_date:
            history.append({"date": current_date.strftime("%Y-%m-%d"), "tokens": 0})
            current_date += timedelta(days=1)

        return {
            "username": username,
            "history": history,
            "period_start": start_date.strftime("%Y-%m-%d"),
            "period_end": end_date.strftime("%Y-%m-%d"),
        }

    def get_all_users_token_usage(self) -> list[dict[str, Any]]:
        """全ユーザーのトークン使用量を取得する (上位20人).

        Returns:
            ユーザー毎の今日・今週・今月のトークン使用量リスト
            トークン使用量が多い順でソートして上位20人を返却

        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # 日付の基準を計算
                now = self._get_now()
                today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
                week_start = today_start - timedelta(days=today_start.weekday())
                month_start = today_start.replace(day=1)

                # 全ユーザーの今月のトークン数を取得 (上位20人)
                cursor.execute(
                    """
                    SELECT user, SUM(total_tokens) as month_total
                    FROM tasks
                    WHERE user IS NOT NULL AND created_at >= ?
                    GROUP BY user
                    ORDER BY month_total DESC
                    LIMIT ?
                    """,
                    (month_start.isoformat(), self.MAX_USERS_LIMIT),
                )

                top_users = [row["user"] for row in cursor.fetchall()]

                if not top_users:
                    return []

                # 各ユーザーの詳細を取得
                results = []
                for username in top_users:
                    today_tokens = self._get_tokens_since(
                        cursor, username, today_start.isoformat(),
                    )
                    week_tokens = self._get_tokens_since(
                        cursor, username, week_start.isoformat(),
                    )
                    month_tokens = self._get_tokens_since(
                        cursor, username, month_start.isoformat(),
                    )

                    # 累計トークン数を取得
                    cursor.execute(
                        """
                        SELECT COALESCE(SUM(total_tokens), 0) as total
                        FROM tasks
                        WHERE user = ?
                        """,
                        (username,),
                    )
                    total_result = cursor.fetchone()
                    total_tokens = max(0, total_result["total"]) if total_result else 0

                    results.append({
                        "username": username,
                        "today": today_tokens,
                        "this_week": week_tokens,
                        "this_month": month_tokens,
                        "total": total_tokens,
                    })

                return results

        except FileNotFoundError:
            logger.warning("tasks.db not found, returning empty list")
            return []
        except sqlite3.Error:
            logger.exception("Database error while getting all users token usage")
            return []
