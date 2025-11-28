"""トークン使用量サービスのテスト."""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

# 親ディレクトリをPythonパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.services.token_usage_service import TokenUsageService


@pytest.fixture
def temp_tasks_db() -> Path:
    """テスト用のtasks.dbを作成する."""
    # 一時ディレクトリにtasks.dbを作成
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    # テーブルを作成
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE tasks (
            uuid TEXT PRIMARY KEY,
            task_source TEXT NOT NULL,
            owner TEXT NOT NULL,
            repo TEXT NOT NULL,
            task_type TEXT NOT NULL,
            task_id TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT,
            process_id INTEGER,
            hostname TEXT,
            llm_provider TEXT,
            model TEXT,
            context_length INTEGER,
            llm_call_count INTEGER DEFAULT 0,
            tool_call_count INTEGER DEFAULT 0,
            total_tokens INTEGER DEFAULT 0,
            compression_count INTEGER DEFAULT 0,
            error_message TEXT,
            user TEXT
        )
    """)
    conn.commit()
    conn.close()

    yield db_path

    # クリーンアップ
    if db_path.exists():
        db_path.unlink()


def insert_test_task(
    db_path: Path,
    user: str,
    total_tokens: int,
    created_at: datetime,
    uuid: str | None = None,
) -> None:
    """テスト用のタスクデータを挿入する."""
    import uuid as uuid_module

    if uuid is None:
        uuid = str(uuid_module.uuid4())

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO tasks (
            uuid, task_source, owner, repo, task_type, task_id,
            status, created_at, total_tokens, user
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            uuid,
            "github",
            "owner",
            "repo",
            "issue",
            "1",
            "completed",
            created_at.isoformat(),
            total_tokens,
            user,
        ),
    )
    conn.commit()
    conn.close()


class TestTokenUsageService:
    """トークン使用量サービスのテストクラス."""

    def test_get_user_token_usage_empty_db(self, temp_tasks_db: Path) -> None:
        """空のデータベースでのトークン使用量取得テスト."""
        service = TokenUsageService(temp_tasks_db)
        result = service.get_user_token_usage("testuser")

        assert result["username"] == "testuser"
        assert result["today"] == 0
        assert result["this_week"] == 0
        assert result["this_month"] == 0
        assert "last_updated" in result

    def test_get_user_token_usage_with_data(self, temp_tasks_db: Path) -> None:
        """データありでのトークン使用量取得テスト."""
        now = datetime.now()

        # 今日のデータ
        insert_test_task(temp_tasks_db, "testuser", 1000, now)

        # 昨日のデータ
        yesterday = now - timedelta(days=1)
        insert_test_task(temp_tasks_db, "testuser", 2000, yesterday)

        # 先週のデータ（今週に含まれない場合）
        last_week = now - timedelta(days=10)
        insert_test_task(temp_tasks_db, "testuser", 3000, last_week)

        service = TokenUsageService(temp_tasks_db)
        result = service.get_user_token_usage("testuser")

        assert result["username"] == "testuser"
        assert result["today"] == 1000
        # 今週と今月は日付によって結果が変わるため、0より大きいことを確認
        assert result["this_week"] >= 1000
        assert result["this_month"] >= 1000

    def test_get_user_token_usage_different_users(self, temp_tasks_db: Path) -> None:
        """異なるユーザーのデータが混在している場合のテスト."""
        now = datetime.now()

        insert_test_task(temp_tasks_db, "user1", 1000, now)
        insert_test_task(temp_tasks_db, "user2", 2000, now)

        service = TokenUsageService(temp_tasks_db)

        result1 = service.get_user_token_usage("user1")
        result2 = service.get_user_token_usage("user2")

        assert result1["today"] == 1000
        assert result2["today"] == 2000

    def test_get_user_daily_history_empty_db(self, temp_tasks_db: Path) -> None:
        """空のデータベースでの日次履歴取得テスト."""
        service = TokenUsageService(temp_tasks_db)
        result = service.get_user_daily_history("testuser", days=7)

        assert result["username"] == "testuser"
        assert len(result["history"]) == 7
        assert all(h["tokens"] == 0 for h in result["history"])
        assert "period_start" in result
        assert "period_end" in result

    def test_get_user_daily_history_with_data(self, temp_tasks_db: Path) -> None:
        """データありでの日次履歴取得テスト."""
        now = datetime.now()
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # 今日と昨日にデータを挿入
        insert_test_task(temp_tasks_db, "testuser", 1000, today + timedelta(hours=10))
        insert_test_task(temp_tasks_db, "testuser", 500, today + timedelta(hours=14))
        insert_test_task(
            temp_tasks_db, "testuser", 2000, today - timedelta(days=1) + timedelta(hours=10)
        )

        service = TokenUsageService(temp_tasks_db)
        result = service.get_user_daily_history("testuser", days=7)

        assert result["username"] == "testuser"
        assert len(result["history"]) == 7

        # 最新の日のデータを確認
        today_str = today.strftime("%Y-%m-%d")
        yesterday_str = (today - timedelta(days=1)).strftime("%Y-%m-%d")

        history_dict = {h["date"]: h["tokens"] for h in result["history"]}

        assert history_dict[today_str] == 1500  # 1000 + 500
        assert history_dict[yesterday_str] == 2000

    def test_get_user_daily_history_days_limit(self, temp_tasks_db: Path) -> None:
        """日数制限のテスト."""
        service = TokenUsageService(temp_tasks_db)

        # 最小値
        result = service.get_user_daily_history("testuser", days=0)
        assert len(result["history"]) == 1  # 最小1日

        # 最大値
        result = service.get_user_daily_history("testuser", days=500)
        assert len(result["history"]) == 365  # 最大365日

    def test_get_all_users_token_usage_empty_db(self, temp_tasks_db: Path) -> None:
        """空のデータベースでの全ユーザートークン取得テスト."""
        service = TokenUsageService(temp_tasks_db)
        result = service.get_all_users_token_usage()

        assert result == []

    def test_get_all_users_token_usage_with_data(self, temp_tasks_db: Path) -> None:
        """データありでの全ユーザートークン取得テスト."""
        now = datetime.now()

        # 複数ユーザーのデータを挿入
        insert_test_task(temp_tasks_db, "user1", 1000, now)
        insert_test_task(temp_tasks_db, "user2", 3000, now)
        insert_test_task(temp_tasks_db, "user3", 2000, now)

        service = TokenUsageService(temp_tasks_db)
        result = service.get_all_users_token_usage()

        assert len(result) == 3

        # トークン数の多い順にソートされていることを確認
        usernames = [r["username"] for r in result]
        assert usernames == ["user2", "user3", "user1"]

    def test_get_all_users_token_usage_limit_20(self, temp_tasks_db: Path) -> None:
        """上位20人制限のテスト."""
        now = datetime.now()

        # 25人分のデータを挿入
        for i in range(25):
            insert_test_task(temp_tasks_db, f"user{i:02d}", 1000 * (25 - i), now)

        service = TokenUsageService(temp_tasks_db)
        result = service.get_all_users_token_usage()

        assert len(result) == 20

    def test_get_all_users_token_usage_includes_total(self, temp_tasks_db: Path) -> None:
        """累計トークン数が含まれることを確認するテスト."""
        now = datetime.now()
        old_date = now - timedelta(days=60)  # 2ヶ月前

        # 今月と過去のデータを挿入
        insert_test_task(temp_tasks_db, "testuser", 1000, now, uuid="uuid1")
        insert_test_task(temp_tasks_db, "testuser", 5000, old_date, uuid="uuid2")

        service = TokenUsageService(temp_tasks_db)
        result = service.get_all_users_token_usage()

        assert len(result) == 1
        assert result[0]["total"] == 6000  # 累計
        assert result[0]["this_month"] == 1000  # 今月のみ

    def test_negative_tokens_handled(self, temp_tasks_db: Path) -> None:
        """負のトークン数が0として扱われることを確認するテスト."""
        now = datetime.now()

        # 負のトークン数を挿入
        conn = sqlite3.connect(str(temp_tasks_db))
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO tasks (
                uuid, task_source, owner, repo, task_type, task_id,
                status, created_at, total_tokens, user
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "test-uuid",
                "github",
                "owner",
                "repo",
                "issue",
                "1",
                "completed",
                now.isoformat(),
                -100,  # 負のトークン数
                "testuser",
            ),
        )
        conn.commit()
        conn.close()

        service = TokenUsageService(temp_tasks_db)
        result = service.get_user_token_usage("testuser")

        # 負の値は0として扱われる
        assert result["today"] >= 0

    def test_db_not_found_returns_empty(self) -> None:
        """データベースが見つからない場合のテスト."""
        service = TokenUsageService("/nonexistent/path/tasks.db")

        # エラーではなく空のデータを返す
        result = service.get_user_token_usage("testuser")
        assert result["today"] == 0

        history = service.get_user_daily_history("testuser")
        assert all(h["tokens"] == 0 for h in history["history"])

        users = service.get_all_users_token_usage()
        assert users == []
