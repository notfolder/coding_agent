"""TaskContextManagerのデータベース登録機能のテスト.

PostgreSQLへの移行に伴い、TaskDBManagerをモック化してテストを実行します。
"""

import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

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
            "base_dir": str(temp_base_dir),
            "compression_threshold": 0.7,
        },
        "context_inheritance": {
            "enabled": False,
        },
        "database": {
            "host": "localhost",
            "port": 5432,
            "name": "test_db",
            "user": "test",
            "password": "test",
        },
    }


@pytest.fixture
def mock_db_task():
    """モックDBTaskを作成するフィクスチャ."""
    db_task = MagicMock()
    db_task.uuid = str(uuid.uuid4())
    db_task.status = "running"
    db_task.task_source = "github"
    db_task.task_type = "issue"
    db_task.owner = "test-owner"
    db_task.repo = "test-repo"
    db_task.number = 123
    db_task.llm_call_count = 0
    db_task.tool_call_count = 0
    db_task.total_tokens = 0
    db_task.compression_count = 0
    return db_task


class TestTaskContextDBRegistration:
    """TaskContextManagerのデータベース登録テスト."""

    @patch("context_storage.task_context_manager.TaskDBManager")
    def test_github_task_registration(self, mock_db_manager_class, temp_base_dir, mock_config, mock_db_task):
        """GitHubタスクがデータベースに正しく登録されることを確認."""
        # モック設定
        mock_db_manager = mock_db_manager_class.return_value
        mock_db_manager.create_task.return_value = mock_db_task
        mock_db_manager.get_task.return_value = mock_db_task
        mock_db_manager.save_task.return_value = mock_db_task
        
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

        # Assert - create_taskが呼ばれたことを確認
        mock_db_manager.create_task.assert_called_once()
        call_args = mock_db_manager.create_task.call_args[0][0]  # 最初の位置引数
        
        assert call_args["task_source"] == "github"
        assert call_args["task_type"] == "issue"
        assert call_args["owner"] == "test-owner"
        assert call_args["repo"] == "test-repo"
        assert call_args["number"] == 123
        assert call_args["status"] == "running"
        assert call_args["user"] == "test-user"

    @patch("context_storage.task_context_manager.TaskDBManager")
    def test_gitlab_task_registration(self, mock_db_manager_class, temp_base_dir, mock_config, mock_db_task):
        """GitLabタスクがデータベースに正しく登録されることを確認."""
        # モックDBTaskをGitLab用に設定
        mock_db_task.task_source = "gitlab"
        mock_db_task.task_type = "issue"
        mock_db_task.project_id = 456
        mock_db_task.owner = None
        mock_db_task.repo = None
        
        mock_db_manager = mock_db_manager_class.return_value
        mock_db_manager.create_task.return_value = mock_db_task
        mock_db_manager.get_task.return_value = mock_db_task
        mock_db_manager.save_task.return_value = mock_db_task
        
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

        # Assert
        mock_db_manager.create_task.assert_called_once()
        call_args = mock_db_manager.create_task.call_args[0][0]
        
        assert call_args["task_source"] == "gitlab"
        assert call_args["task_type"] == "issue"
        assert call_args["project_id"] == 456
        assert call_args["number"] == 789

    @patch("context_storage.task_context_manager.TaskDBManager")
    def test_task_completion_updates_db(self, mock_db_manager_class, temp_base_dir, mock_config, mock_db_task):
        """タスク完了時にデータベースが更新されることを確認."""
        mock_db_manager = mock_db_manager_class.return_value
        mock_db_manager.create_task.return_value = mock_db_task
        mock_db_manager.get_task.return_value = mock_db_task
        mock_db_manager.save_task.return_value = mock_db_task
        
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

        # Assert - save_taskが呼ばれたことを確認（完了時に保存）
        assert mock_db_manager.save_task.called
        # モックDBTaskのstatusがcompletedに設定されたことを確認
        assert mock_db_task.status == "completed"
        assert mock_db_task.completed_at is not None

    @patch("context_storage.task_context_manager.TaskDBManager")
    def test_task_failure_updates_db(self, mock_db_manager_class, temp_base_dir, mock_config, mock_db_task):
        """タスク失敗時にデータベースが更新されることを確認."""
        mock_db_manager = mock_db_manager_class.return_value
        mock_db_manager.create_task.return_value = mock_db_task
        mock_db_manager.get_task.return_value = mock_db_task
        mock_db_manager.save_task.return_value = mock_db_task
        
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
        assert mock_db_manager.save_task.called
        assert mock_db_task.status == "failed"
        assert mock_db_task.error_message == error_msg
        assert mock_db_task.completed_at is not None

    @patch("context_storage.task_context_manager.TaskDBManager")
    def test_multiple_tasks_same_issue(self, mock_db_manager_class, temp_base_dir, mock_config, mock_db_task):
        """同じIssueで複数回実行された場合、各タスクがcreate_taskされることを確認."""
        mock_db_manager = mock_db_manager_class.return_value
        mock_db_manager.create_task.return_value = mock_db_task
        mock_db_manager.get_task.return_value = mock_db_task
        mock_db_manager.save_task.return_value = mock_db_task
        
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

        # Assert - create_taskが2回呼ばれたことを確認
        assert mock_db_manager.create_task.call_count == 2

    @patch("context_storage.task_context_manager.TaskDBManager")
    def test_statistics_update(self, mock_db_manager_class, temp_base_dir, mock_config, mock_db_task):
        """統計情報の更新がDBに反映されることを確認."""
        mock_db_manager = mock_db_manager_class.return_value
        mock_db_manager.create_task.return_value = mock_db_task
        mock_db_manager.get_task.return_value = mock_db_task
        mock_db_manager.save_task.return_value = mock_db_task
        
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

        # Assert - save_taskが呼ばれたことを確認（統計更新時に保存）
        assert mock_db_manager.save_task.called
        # モックDBTaskの統計が更新されたことを確認
        assert mock_db_task.llm_call_count == 5
        assert mock_db_task.tool_call_count == 10
        assert mock_db_task.total_tokens == 1000
        assert mock_db_task.compression_count == 2
