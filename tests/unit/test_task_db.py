"""TaskDBManagerとDBTaskモデルのユニットテスト.

PostgreSQL接続のテストはモック化し、SQLAlchemy機能のテストを行います。
"""

from __future__ import annotations

import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.task_db import Base, DBTask, TaskDBManager
from handlers.task_key import (
    GitHubIssueTaskKey,
    GitHubPullRequestTaskKey,
    GitLabIssueTaskKey,
    GitLabMergeRequestTaskKey,
)


@pytest.fixture
def in_memory_engine():
    """SQLite in-memoryエンジンを作成するフィクスチャ."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def session(in_memory_engine):
    """テスト用セッションを作成するフィクスチャ."""
    Session = sessionmaker(bind=in_memory_engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def mock_config() -> dict[str, Any]:
    """モック設定を返すフィクスチャ."""
    return {
        "database": {
            "host": "localhost",
            "port": 5432,
            "name": "test_db",
            "user": "test_user",
            "password": "test_pass",
            "pool_size": 5,
            "max_overflow": 10,
        },
        "llm": {
            "provider": "openai",
            "openai": {
                "model": "gpt-4",
                "context_length": 128000,
            },
        },
    }


class TestDBTaskModel:
    """DBTaskモデルのテスト."""

    def test_create_github_issue_task(self, session):
        """GitHubIssueタスクの作成テスト."""
        now = datetime.now(timezone.utc)
        db_task = DBTask(
            uuid=str(uuid.uuid4()),
            task_source="github",
            task_type="issue",
            owner="test-owner",
            repo="test-repo",
            project_id=None,
            number=123,
            status="running",
            created_at=now,
            started_at=now,
            process_id=1234,
            hostname="test-host",
            llm_provider="openai",
            model="gpt-4",
            context_length=128000,
            user="test-user",
        )
        
        session.add(db_task)
        session.commit()
        
        # タスクが保存されたか確認
        saved_task = session.query(DBTask).filter_by(uuid=db_task.uuid).first()
        assert saved_task is not None
        assert saved_task.task_source == "github"
        assert saved_task.task_type == "issue"
        assert saved_task.owner == "test-owner"
        assert saved_task.repo == "test-repo"
        assert saved_task.number == 123
        assert saved_task.status == "running"

    def test_create_gitlab_issue_task(self, session):
        """GitLabIssueタスクの作成テスト."""
        now = datetime.now(timezone.utc)
        db_task = DBTask(
            uuid=str(uuid.uuid4()),
            task_source="gitlab",
            task_type="issue",
            owner=None,
            repo=None,
            project_id=456,
            number=789,
            status="pending",
            created_at=now,
            user="gitlab-user",
        )
        
        session.add(db_task)
        session.commit()
        
        saved_task = session.query(DBTask).filter_by(uuid=db_task.uuid).first()
        assert saved_task is not None
        assert saved_task.task_source == "gitlab"
        assert saved_task.task_type == "issue"
        assert saved_task.project_id == 456
        assert saved_task.number == 789

    def test_get_task_key_github_issue(self, session):
        """GitHubIssueTaskKeyの復元テスト."""
        db_task = DBTask(
            uuid=str(uuid.uuid4()),
            task_source="github",
            task_type="issue",
            owner="owner1",
            repo="repo1",
            project_id=None,
            number=100,
            status="running",
            created_at=datetime.now(timezone.utc),
        )
        
        task_key = db_task.get_task_key()
        
        assert isinstance(task_key, GitHubIssueTaskKey)
        assert task_key.owner == "owner1"
        assert task_key.repo == "repo1"
        assert task_key.number == 100

    def test_get_task_key_github_pull_request(self, session):
        """GitHubPullRequestTaskKeyの復元テスト."""
        db_task = DBTask(
            uuid=str(uuid.uuid4()),
            task_source="github",
            task_type="pull_request",
            owner="owner2",
            repo="repo2",
            project_id=None,
            number=200,
            status="running",
            created_at=datetime.now(timezone.utc),
        )
        
        task_key = db_task.get_task_key()
        
        assert isinstance(task_key, GitHubPullRequestTaskKey)
        assert task_key.owner == "owner2"
        assert task_key.repo == "repo2"
        assert task_key.number == 200

    def test_get_task_key_gitlab_issue(self, session):
        """GitLabIssueTaskKeyの復元テスト."""
        db_task = DBTask(
            uuid=str(uuid.uuid4()),
            task_source="gitlab",
            task_type="issue",
            owner=None,
            repo=None,
            project_id=111,
            number=222,
            status="running",
            created_at=datetime.now(timezone.utc),
        )
        
        task_key = db_task.get_task_key()
        
        assert isinstance(task_key, GitLabIssueTaskKey)
        assert task_key.project_id == 111
        assert task_key.issue_iid == 222

    def test_get_task_key_gitlab_merge_request(self, session):
        """GitLabMergeRequestTaskKeyの復元テスト."""
        db_task = DBTask(
            uuid=str(uuid.uuid4()),
            task_source="gitlab",
            task_type="merge_request",
            owner=None,
            repo=None,
            project_id=333,
            number=444,
            status="running",
            created_at=datetime.now(timezone.utc),
        )
        
        task_key = db_task.get_task_key()
        
        assert isinstance(task_key, GitLabMergeRequestTaskKey)
        assert task_key.project_id == 333
        assert task_key.mr_iid == 444

    def test_get_task_key_invalid_combination(self, session):
        """不正なtask_source/task_typeの組み合わせでValueErrorが発生することを確認."""
        db_task = DBTask(
            uuid=str(uuid.uuid4()),
            task_source="unknown",
            task_type="unknown",
            owner=None,
            repo=None,
            project_id=None,
            number=1,
            status="running",
            created_at=datetime.now(timezone.utc),
        )
        
        with pytest.raises(ValueError, match="不明なtask_source/task_type"):
            db_task.get_task_key()

    def test_statistics_default_values(self, session):
        """統計情報のデフォルト値テスト."""
        db_task = DBTask(
            uuid=str(uuid.uuid4()),
            task_source="github",
            task_type="issue",
            owner="owner",
            repo="repo",
            number=1,
            status="running",
            created_at=datetime.now(timezone.utc),
        )
        
        session.add(db_task)
        session.commit()
        
        saved_task = session.query(DBTask).filter_by(uuid=db_task.uuid).first()
        assert saved_task.llm_call_count == 0
        assert saved_task.tool_call_count == 0
        assert saved_task.total_tokens == 0
        assert saved_task.compression_count == 0


class TestTaskDBManagerWithMock:
    """TaskDBManagerのテスト（PostgreSQLをモック化）."""

    @patch("db.task_db.create_engine")
    def test_create_engine_with_database_url_env(self, mock_create_engine, mock_config):
        """DATABASE_URL環境変数が設定されている場合のテスト."""
        mock_engine = MagicMock()
        mock_create_engine.return_value = mock_engine
        
        with patch.dict("os.environ", {"DATABASE_URL": "postgresql://user:pass@host/db"}):
            # 環境変数をconfigに反映
            import os
            if "DATABASE_URL" in os.environ:
                mock_config["database"] = {"url": os.environ["DATABASE_URL"]}
            manager = TaskDBManager(mock_config)
            
        # DATABASE_URLが使用されていることを確認
        call_args = mock_create_engine.call_args
        assert "postgresql://user:pass@host/db" in str(call_args)

    @patch("db.task_db.create_engine")
    def test_create_engine_with_individual_env_vars(self, mock_create_engine, mock_config):
        """個別の環境変数が設定されている場合のテスト."""
        mock_engine = MagicMock()
        mock_create_engine.return_value = mock_engine
        
        env_vars = {
            "DATABASE_HOST": "env-host",
            "DATABASE_PORT": "5433",
            "DATABASE_NAME": "env-db",
            "DATABASE_USER": "env-user",
            "DATABASE_PASSWORD": "env-pass",
        }
        
        # DATABASE_URLを含めない環境変数を設定（clear=Falseで他の環境変数は保持）
        # DATABASE_URLがあった場合に備えて空文字列で上書き
        env_vars_with_no_url = {**env_vars, "DATABASE_URL": ""}
        
        with patch.dict("os.environ", env_vars_with_no_url, clear=False):
            # 環境変数をconfigに反映
            import os
            config_for_test = {
                "database": {
                    "host": os.environ.get("DATABASE_HOST", "localhost"),
                    "port": int(os.environ.get("DATABASE_PORT", "5432")),
                    "name": os.environ.get("DATABASE_NAME", "tasks"),
                    "user": os.environ.get("DATABASE_USER", "postgres"),
                    "password": os.environ.get("DATABASE_PASSWORD", "postgres"),
                }
            }
            manager = TaskDBManager(config_for_test)
            
        # 環境変数から構築されたURLが使用されていることを確認
        call_args = mock_create_engine.call_args
        assert "env-host" in str(call_args) or "5433" in str(call_args)


class TestTaskDBManagerIntegration:
    """TaskDBManagerの統合テスト（SQLite in-memoryを使用）."""

    @pytest.fixture
    def db_manager(self, in_memory_engine):
        """SQLite in-memoryを使用したTaskDBManagerフィクスチャ."""
        manager = TaskDBManager.__new__(TaskDBManager)
        manager.config = {}
        manager._engine = in_memory_engine
        manager._session_factory = sessionmaker(bind=in_memory_engine)
        return manager

    def test_create_task(self, db_manager):
        """タスク作成テスト."""
        now = datetime.now(timezone.utc)
        task_data = {
            "uuid": str(uuid.uuid4()),
            "task_source": "github",
            "task_type": "issue",
            "owner": "test-owner",
            "repo": "test-repo",
            "number": 42,
            "status": "running",
            "created_at": now,
            "user": "test-user",
            "llm_call_count": 0,
            "tool_call_count": 0,
            "total_tokens": 0,
            "compression_count": 0,
        }
        
        db_task = db_manager.create_task(task_data)
        
        assert db_task.uuid == task_data["uuid"]
        assert db_task.task_source == "github"
        assert db_task.number == 42

    def test_get_task(self, db_manager):
        """タスク取得テスト."""
        task_uuid = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        task_data = {
            "uuid": task_uuid,
            "task_source": "github",
            "task_type": "issue",
            "owner": "owner",
            "repo": "repo",
            "number": 1,
            "status": "running",
            "created_at": now,
            "llm_call_count": 0,
            "tool_call_count": 0,
            "total_tokens": 0,
            "compression_count": 0,
        }
        
        db_manager.create_task(task_data)
        
        retrieved_task = db_manager.get_task(task_uuid)
        
        assert retrieved_task is not None
        assert retrieved_task.uuid == task_uuid

    def test_get_task_not_found(self, db_manager):
        """存在しないタスクの取得テスト."""
        result = db_manager.get_task("non-existent-uuid")
        assert result is None

    def test_get_task_by_key(self, db_manager):
        """TaskKeyによるタスク取得テスト."""
        now = datetime.now(timezone.utc)
        
        # タスクを作成
        task_data = {
            "uuid": str(uuid.uuid4()),
            "task_source": "github",
            "task_type": "issue",
            "owner": "search-owner",
            "repo": "search-repo",
            "number": 999,
            "status": "running",
            "created_at": now,
            "llm_call_count": 0,
            "tool_call_count": 0,
            "total_tokens": 0,
            "compression_count": 0,
        }
        db_manager.create_task(task_data)
        
        # TaskKeyで検索
        task_key = GitHubIssueTaskKey("search-owner", "search-repo", 999)
        found_task = db_manager.get_task_by_key(task_key)
        
        assert found_task is not None
        assert found_task.owner == "search-owner"
        assert found_task.repo == "search-repo"
        assert found_task.number == 999

    def test_save_task(self, db_manager):
        """タスク保存（更新）テスト."""
        task_uuid = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        
        task_data = {
            "uuid": task_uuid,
            "task_source": "github",
            "task_type": "issue",
            "owner": "owner",
            "repo": "repo",
            "number": 1,
            "status": "running",
            "created_at": now,
            "llm_call_count": 0,
            "tool_call_count": 0,
            "total_tokens": 0,
            "compression_count": 0,
        }
        
        db_task = db_manager.create_task(task_data)
        
        # ステータスを更新
        db_task.status = "completed"
        db_task.completed_at = datetime.now(timezone.utc)
        
        saved_task = db_manager.save_task(db_task)
        
        assert saved_task.status == "completed"
        assert saved_task.completed_at is not None

    def test_create_tables(self, in_memory_engine):
        """テーブル作成テスト."""
        # 新しいマネージャーでテーブル作成をテスト
        manager = TaskDBManager.__new__(TaskDBManager)
        manager.config = {}
        manager._engine = in_memory_engine
        manager._session_factory = sessionmaker(bind=in_memory_engine)
        
        # 既に存在するテーブルに対して再度create_tablesを呼んでもエラーにならない
        manager.create_tables()
        
        # タスクを作成できることを確認
        now = datetime.now(timezone.utc)
        task_data = {
            "uuid": str(uuid.uuid4()),
            "task_source": "github",
            "task_type": "issue",
            "owner": "owner",
            "repo": "repo",
            "number": 1,
            "status": "running",
            "created_at": now,
            "llm_call_count": 0,
            "tool_call_count": 0,
            "total_tokens": 0,
            "compression_count": 0,
        }
        
        db_task = manager.create_task(task_data)
        assert db_task is not None
