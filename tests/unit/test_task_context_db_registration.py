"""TaskContextManagerのデータベース登録機能のテスト."""

import sqlite3
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from context_storage.task_context_manager import TaskContextManager
from handlers.task_key import GitHubIssueTaskKey, GitLabIssueTaskKey


@pytest.fixture
def temp_base_dir():
    """一時ディレクトリを作成するフィクスチャ."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_config(temp_base_dir):
    """モック設定を返すフィクスチャ."""
    return {
        "llm": {
            "provider": "openai",
            "openai": {
                "model": "gpt-4",
                "context_length": 128000,
            },
        },
        "context_storage": {
            "base_dir": str(temp_base_dir),  # base_dirをconfigに含める
            "compression_threshold": 0.7,
        },
        "context_inheritance": {
            "enabled": False,  # テスト中は無効化
        },
    }


class TestTaskContextDBRegistration:
    """TaskContextManagerのデータベース登録テスト."""

    def test_github_task_registration(self, temp_base_dir, mock_config):
        """GitHubタスクがデータベースに正しく登録されることを確認."""
        # Arrange
        task_key = GitHubIssueTaskKey("test-owner", "test-repo", 123)
        task_uuid = str(uuid.uuid4())
        user = "test-user"

        # Act
        context_manager = TaskContextManager(
            task_key=task_key,
            task_uuid=task_uuid,
            config=mock_config,
            user=user,
        )

        # Assert - データベースにレコードが作成されているか確認
        db_path = temp_base_dir / "tasks.db"
        assert db_path.exists(), "データベースファイルが作成されていません"

        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT uuid, task_source, owner, repo, task_type, task_id, status, user
                   FROM tasks WHERE uuid = ?""",
                (context_manager.uuid,),
            )
            row = cursor.fetchone()

        assert row is not None, "タスクがデータベースに登録されていません"
        uuid_db, task_source, owner, repo, task_type, task_id, status, user_db = row

        assert task_source == "github", f"task_sourceが不正: {task_source}"
        assert owner == "test-owner", f"ownerが不正: {owner}"
        assert repo == "test-repo", f"repoが不正: {repo}"
        assert task_type == "issue", f"task_typeが不正: {task_type}"
        assert task_id == "123", f"task_idが不正: {task_id}"
        assert status == "running", f"statusが不正: {status}"
        assert user_db == "test-user", f"userが不正: {user_db}"

    def test_gitlab_task_registration(self, temp_base_dir, mock_config):
        """GitLabタスクがデータベースに正しく登録されることを確認."""
        # Arrange
        task_key = GitLabIssueTaskKey(project_id=456, issue_iid=789)
        task_uuid = str(uuid.uuid4())
        user = "gitlab-user"

        # Act
        context_manager = TaskContextManager(
            task_key=task_key,
            task_uuid=task_uuid,
            config=mock_config,
            user=user,
        )

        # Assert - データベースにレコードが作成されているか確認
        db_path = temp_base_dir / "tasks.db"
        assert db_path.exists(), "データベースファイルが作成されていません"

        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT uuid, task_source, owner, repo, task_type, task_id, status, user
                   FROM tasks WHERE uuid = ?""",
                (context_manager.uuid,),
            )
            row = cursor.fetchone()

        assert row is not None, "タスクがデータベースに登録されていません"
        uuid_db, task_source, owner, repo, task_type, task_id, status, user_db = row

        assert task_source == "gitlab", f"task_sourceが不正: {task_source}"
        assert owner == "", f"owner（GitLabでは空）が不正: {owner}"
        assert repo == "456", f"repo（project_id）が不正: {repo}"
        assert task_type == "issue", f"task_typeが不正: {task_type}"
        assert task_id == "789", f"task_id（issue_iid）が不正: {task_id}"
        assert status == "running", f"statusが不正: {status}"
        assert user_db == "gitlab-user", f"userが不正: {user_db}"

    def test_task_completion_updates_db(self, temp_base_dir, mock_config):
        """タスク完了時にデータベースが更新されることを確認."""
        # Arrange
        task_key = GitHubIssueTaskKey("owner", "repo", 1)
        task_uuid = str(uuid.uuid4())
        context_manager = TaskContextManager(
            task_key=task_key,
            task_uuid=task_uuid,
            config=mock_config,
            user="user",
        )

        # Act
        context_manager.complete()

        # Assert
        db_path = temp_base_dir / "tasks.db"
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT status, completed_at FROM tasks WHERE uuid = ?",
                (context_manager.uuid,),
            )
            row = cursor.fetchone()

        assert row is not None
        status, completed_at = row
        assert status == "completed", f"完了後のstatusが不正: {status}"
        assert completed_at is not None, "completed_atが設定されていません"

        # completed_atが有効なISO形式の日時であることを確認
        try:
            datetime.fromisoformat(completed_at)
        except ValueError:
            pytest.fail(f"completed_atが無効な形式: {completed_at}")

    def test_task_failure_updates_db(self, temp_base_dir, mock_config):
        """タスク失敗時にデータベースが更新されることを確認."""
        # Arrange
        task_key = GitHubIssueTaskKey("owner", "repo", 2)
        task_uuid = str(uuid.uuid4())
        context_manager = TaskContextManager(
            task_key=task_key,
            task_uuid=task_uuid,
            config=mock_config,
            user="user",
        )
        error_msg = "Test error message"

        # Act
        context_manager.fail(error_msg)

        # Assert
        db_path = temp_base_dir / "tasks.db"
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT status, error_message, completed_at FROM tasks WHERE uuid = ?",
                (context_manager.uuid,),
            )
            row = cursor.fetchone()

        assert row is not None
        status, error_message, completed_at = row
        assert status == "failed", f"失敗後のstatusが不正: {status}"
        assert error_message == error_msg, f"error_messageが不正: {error_message}"
        assert completed_at is not None, "completed_atが設定されていません"

    def test_multiple_tasks_same_issue(self, temp_base_dir, mock_config):
        """同じIssueで複数回実行された場合、複数のレコードが作成されることを確認."""
        # Arrange
        task_key = GitHubIssueTaskKey("owner", "repo", 100)

        # Act - 1回目
        task_uuid1 = str(uuid.uuid4())
        context_manager1 = TaskContextManager(
            task_key=task_key,
            task_uuid=task_uuid1,
            config=mock_config,
            user="user1",
        )
        context_manager1.complete()

        # Act - 2回目（異なるUUID）
        task_uuid2 = str(uuid.uuid4())
        context_manager2 = TaskContextManager(
            task_key=task_key,
            task_uuid=task_uuid2,
            config=mock_config,
            user="user2",
        )
        context_manager2.complete()

        # Assert
        db_path = temp_base_dir / "tasks.db"
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT uuid, status FROM tasks
                   WHERE task_source = 'github'
                     AND owner = 'owner'
                     AND repo = 'repo'
                     AND task_type = 'issue'
                     AND task_id = '100'
                   ORDER BY created_at""",
            )
            rows = cursor.fetchall()

        assert len(rows) == 2, f"2つのレコードが期待されるが、{len(rows)}件でした"
        assert rows[0][1] == "completed", "1回目のstatusが不正"
        assert rows[1][1] == "completed", "2回目のstatusが不正"
        assert rows[0][0] != rows[1][0], "UUIDが重複しています"

    def test_statistics_update(self, temp_base_dir, mock_config):
        """統計情報の更新がデータベースに反映されることを確認."""
        # Arrange
        task_key = GitHubIssueTaskKey("owner", "repo", 3)
        task_uuid = str(uuid.uuid4())
        context_manager = TaskContextManager(
            task_key=task_key,
            task_uuid=task_uuid,
            config=mock_config,
            user="user",
        )

        # Act
        context_manager.update_statistics(llm_calls=5, tool_calls=10, tokens=1000, compressions=2)

        # Assert
        db_path = temp_base_dir / "tasks.db"
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT llm_call_count, tool_call_count, total_tokens, compression_count
                   FROM tasks WHERE uuid = ?""",
                (context_manager.uuid,),
            )
            row = cursor.fetchone()

        assert row is not None
        llm_calls_db, tool_calls_db, tokens_db, compressions_db = row
        assert llm_calls_db == 5, f"llm_call_countが不正: {llm_calls_db}"
        assert tool_calls_db == 10, f"tool_call_countが不正: {tool_calls_db}"
        assert tokens_db == 1000, f"total_tokensが不正: {tokens_db}"
        assert compressions_db == 2, f"compression_countが不正: {compressions_db}"
