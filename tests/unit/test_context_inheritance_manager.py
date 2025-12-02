"""Unit tests for ContextInheritanceManager."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from context_storage.context_inheritance_manager import (
    ContextInheritanceManager,
    InheritanceContext,
    PreviousContext,
)
from handlers.task_key import GitHubIssueTaskKey


class TestContextInheritanceManager(unittest.TestCase):
    """Test ContextInheritanceManager functionality."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.base_dir = self.temp_dir / "contexts"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.completed_dir = self.base_dir / "completed"
        self.completed_dir.mkdir(parents=True, exist_ok=True)

        # テスト用設定
        self.config = {
            "context_inheritance": {
                "enabled": True,
                "context_expiry_days": 90,
                "max_inherited_tokens": 8000,
                "planning": {
                    "inherit_plans": True,
                    "inherit_verifications": True,
                    "inherit_reflections": True,
                    "max_previous_plans": 3,
                    "reuse_successful_patterns": True,
                },
            },
        }

        # テスト用のタスクリストを保持
        self.test_tasks = []

    def tearDown(self) -> None:
        """Clean up test fixtures."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_mock_db_task(
        self,
        uuid: str,
        task_source: str = "github",
        owner: str = "testowner",
        repo: str = "testrepo",
        task_type: str = "issue",
        number: int = 123,
        status: str = "completed",
        completed_at: datetime | None = None,
    ) -> MagicMock:
        """モックDBTaskオブジェクトを作成する."""
        if completed_at is None:
            completed_at = datetime.now(timezone.utc)

        mock_task = MagicMock()
        mock_task.uuid = uuid
        mock_task.task_source = task_source
        mock_task.owner = owner
        mock_task.repo = repo
        mock_task.task_type = task_type
        mock_task.number = number
        mock_task.status = status
        mock_task.created_at = datetime.now(timezone.utc)
        mock_task.completed_at = completed_at

        # get_task_keyメソッドのモック
        if task_source == "github" and task_type == "issue":
            mock_task.get_task_key.return_value = GitHubIssueTaskKey(owner, repo, number)

        return mock_task

    def _add_test_task(
        self,
        uuid: str,
        task_source: str = "github",
        owner: str = "testowner",
        repo: str = "testrepo",
        task_type: str = "issue",
        task_id: str = "123",
        status: str = "completed",
        completed_at: datetime | None = None,
    ) -> None:
        """テスト用タスクをリストに追加する."""
        mock_task = self._create_mock_db_task(
            uuid=uuid,
            task_source=task_source,
            owner=owner,
            repo=repo,
            task_type=task_type,
            number=int(task_id),
            status=status,
            completed_at=completed_at,
        )
        self.test_tasks.append(mock_task)

    def _create_test_context_dir(
        self,
        uuid: str,
        summary_text: str | None = None,
        metadata: dict | None = None,
    ) -> Path:
        """テスト用コンテキストディレクトリを作成する."""
        context_dir = self.completed_dir / uuid
        context_dir.mkdir(parents=True, exist_ok=True)

        # summaries.jsonlを作成
        if summary_text:
            summaries_file = context_dir / "summaries.jsonl"
            summary_entry = {
                "id": 1,
                "start_seq": 1,
                "end_seq": 10,
                "summary": summary_text,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            with summaries_file.open("w") as f:
                f.write(json.dumps(summary_entry) + "\n")

        # metadata.jsonを作成
        if metadata:
            metadata_file = context_dir / "metadata.json"
            with metadata_file.open("w") as f:
                json.dump(metadata, f)

        return context_dir

    def test_init_with_default_config(self) -> None:
        """デフォルト設定での初期化テスト."""
        manager = ContextInheritanceManager(self.base_dir, self.config)

        self.assertTrue(manager.enabled)
        self.assertEqual(manager.expiry_days, 90)
        self.assertEqual(manager.max_inherited_tokens, 8000)
        self.assertTrue(manager.inherit_plans)

    def test_init_with_disabled(self) -> None:
        """無効設定での初期化テスト."""
        config = {"context_inheritance": {"enabled": False}}
        manager = ContextInheritanceManager(self.base_dir, config)

        self.assertFalse(manager.enabled)

    def test_find_previous_contexts_no_database(self) -> None:
        """DBが存在しない場合のテスト."""
        # DBファイルを削除
        db_path = self.base_dir / "tasks.db"
        if db_path.exists():
            db_path.unlink()

        manager = ContextInheritanceManager(self.base_dir, self.config)
        task_key = GitHubIssueTaskKey("testowner", "testrepo", 123)

        results = manager.find_previous_contexts(task_key)
        self.assertEqual(results, [])

    def test_find_previous_contexts_with_matching_task(self) -> None:
        """マッチするタスクがある場合のテスト."""
        # テストデータを作成
        test_uuid = "test-uuid-123"
        self._add_test_task(
            uuid=test_uuid,
            task_source="github",
            owner="testowner",
            repo="testrepo",
            task_type="issue",
            task_id="123",
            status="completed",
        )
        self._create_test_context_dir(
            test_uuid,
            summary_text="Test summary content",
        )

        # TaskDBManagerをモック化
        with patch('db.task_db.TaskDBManager') as mock_db_manager:
            mock_instance = MagicMock()
            mock_db_manager.return_value = mock_instance
            # find_completed_tasks_by_keyが対象タスクを返すようにモック
            mock_instance.find_completed_tasks_by_key.return_value = self.test_tasks

            manager = ContextInheritanceManager(self.base_dir, self.config)
            task_key = GitHubIssueTaskKey("testowner", "testrepo", 123)

            results = manager.find_previous_contexts(task_key)

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].uuid, test_uuid)
            self.assertEqual(results[0].status, "completed")
            self.assertEqual(results[0].final_summary, "Test summary content")

    def test_find_previous_contexts_excludes_failed(self) -> None:
        """失敗タスクが除外されることのテスト."""
        # 失敗タスクを作成
        self._add_test_task(
            uuid="failed-uuid",
            task_source="github",
            owner="testowner",
            repo="testrepo",
            task_type="issue",
            task_id="123",
            status="failed",
        )

        # TaskDBManagerをモック化（failedステータスは除外される想定）
        with patch('db.task_db.TaskDBManager') as mock_db_manager:
            mock_instance = MagicMock()
            mock_db_manager.return_value = mock_instance
            # find_completed_tasks_by_keyはfailedを除外して空リストを返す
            mock_instance.find_completed_tasks_by_key.return_value = []

            manager = ContextInheritanceManager(self.base_dir, self.config)
            task_key = GitHubIssueTaskKey("testowner", "testrepo", 123)

            results = manager.find_previous_contexts(task_key)
            self.assertEqual(len(results), 0)

    def test_find_previous_contexts_excludes_expired(self) -> None:
        """有効期限切れタスクが除外されることのテスト."""
        # 100日前の完了日時を設定
        old_completed_at = datetime.now(timezone.utc) - timedelta(days=100)
        self._add_test_task(
            uuid="old-uuid",
            task_source="github",
            owner="testowner",
            repo="testrepo",
            task_type="issue",
            task_id="123",
            status="completed",
            completed_at=old_completed_at,
        )

        # TaskDBManagerをモック化（期限切れは除外される想定）
        with patch('db.task_db.TaskDBManager') as mock_db_manager:
            mock_instance = MagicMock()
            mock_db_manager.return_value = mock_instance
            # 期限切れタスクは除外されて空リストを返す
            mock_instance.find_completed_tasks_by_key.return_value = []

            manager = ContextInheritanceManager(self.base_dir, self.config)
            task_key = GitHubIssueTaskKey("testowner", "testrepo", 123)

            results = manager.find_previous_contexts(task_key)
            self.assertEqual(len(results), 0)

    def test_get_inheritance_context_with_valid_context(self) -> None:
        """有効なコンテキストの引き継ぎテスト."""
        test_uuid = "test-uuid-456"
        self._add_test_task(
            uuid=test_uuid,
            task_source="github",
            owner="testowner",
            repo="testrepo",
            task_type="issue",
            task_id="123",
        )
        self._create_test_context_dir(
            test_uuid,
            summary_text="Previous execution summary",
        )

        # TaskDBManagerをモック化
        with patch('db.task_db.TaskDBManager') as mock_db_manager:
            mock_instance = MagicMock()
            mock_db_manager.return_value = mock_instance
            mock_instance.find_completed_tasks_by_key.return_value = self.test_tasks

            manager = ContextInheritanceManager(self.base_dir, self.config)
            task_key = GitHubIssueTaskKey("testowner", "testrepo", 123)

            inheritance = manager.get_inheritance_context(task_key)

            self.assertIsNotNone(inheritance)
            self.assertEqual(
                inheritance.final_summary,
                "Previous execution summary",
            )
            self.assertEqual(inheritance.previous_context.uuid, test_uuid)

    def test_get_inheritance_context_no_summary(self) -> None:
        """要約がない場合のテスト."""
        test_uuid = "test-uuid-789"
        self._add_test_task(
            uuid=test_uuid,
            task_source="github",
            owner="testowner",
            repo="testrepo",
            task_type="issue",
            task_id="123",
        )
        # summaries.jsonlを作成しない
        self._create_test_context_dir(test_uuid, summary_text=None)

        # TaskDBManagerをモック化
        with patch('db.task_db.TaskDBManager') as mock_db_manager:
            mock_instance = MagicMock()
            mock_db_manager.return_value = mock_instance
            mock_instance.find_completed_tasks_by_key.return_value = self.test_tasks

            manager = ContextInheritanceManager(self.base_dir, self.config)
            task_key = GitHubIssueTaskKey("testowner", "testrepo", 123)

            inheritance = manager.get_inheritance_context(task_key)
            self.assertIsNone(inheritance)

    def test_get_inheritance_context_disabled(self) -> None:
        """機能が無効な場合のテスト."""
        config = {"context_inheritance": {"enabled": False}}
        manager = ContextInheritanceManager(self.base_dir, config)
        task_key = GitHubIssueTaskKey("testowner", "testrepo", 123)

        inheritance = manager.get_inheritance_context(task_key)
        self.assertIsNone(inheritance)

    def test_create_initial_context(self) -> None:
        """初期コンテキスト生成のテスト."""
        manager = ContextInheritanceManager(self.base_dir, self.config)

        # InheritanceContextを手動で作成
        prev = PreviousContext(
            uuid="test-uuid",
            task_key_dict={"type": "github_issue"},
            status="completed",
            completed_at=datetime.now(timezone.utc),
            final_summary="Previous summary text",
        )
        inheritance = InheritanceContext(
            previous_context=prev,
            final_summary="Previous summary text",
        )

        messages = manager.create_initial_context(
            inheritance,
            "Current user request",
        )

        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["role"], "assistant")
        self.assertIn("前回の処理要約:", messages[0]["content"])
        self.assertIn("Previous summary text", messages[0]["content"])
        self.assertEqual(messages[1]["role"], "user")
        self.assertEqual(messages[1]["content"], "Current user request")

    def test_generate_notification_comment(self) -> None:
        """通知コメント生成のテスト."""
        manager = ContextInheritanceManager(self.base_dir, self.config)

        prev = PreviousContext(
            uuid="abc12345-long-uuid",
            task_key_dict={"type": "github_issue"},
            status="completed",
            completed_at=datetime.now(timezone.utc),
            final_summary="Summary",
        )
        inheritance = InheritanceContext(
            previous_context=prev,
            final_summary="Summary",
        )

        comment = manager.generate_notification_comment(inheritance)

        self.assertIn("過去のコンテキストを引き継ぎました", comment)
        self.assertIn("abc12345", comment)  # UUIDの短縮形
        self.assertIn("引き継ぎ内容: 最終要約", comment)

    def test_truncate_summary_if_needed(self) -> None:
        """要約のトークン制限テスト."""
        config = {
            "context_inheritance": {
                "enabled": True,
                "max_inherited_tokens": 100,  # 400文字相当
            },
        }
        manager = ContextInheritanceManager(self.base_dir, config)

        # 1000文字 = 約250トークンを超える要約（100トークン制限を超える）
        long_summary = "a" * 1000

        truncated = manager._truncate_summary_if_needed(long_summary)

        self.assertTrue(len(truncated) < len(long_summary))
        self.assertIn("省略されました", truncated)

    def test_find_previous_contexts_returns_latest_first(self) -> None:
        """最新のコンテキストが最初に返されることのテスト."""
        # 古いタスク
        old_completed_at = datetime.now(timezone.utc) - timedelta(days=30)
        old_task = self._create_mock_db_task(
            uuid="old-uuid",
            task_source="github",
            owner="testowner",
            repo="testrepo",
            task_type="issue",
            number=123,
            status="completed",
            completed_at=old_completed_at,
        )
        self._create_test_context_dir("old-uuid", summary_text="Old summary")

        # 新しいタスク
        new_completed_at = datetime.now(timezone.utc) - timedelta(days=1)
        new_task = self._create_mock_db_task(
            uuid="new-uuid",
            task_source="github",
            owner="testowner",
            repo="testrepo",
            task_type="issue",
            number=123,
            status="completed",
            completed_at=new_completed_at,
        )
        self._create_test_context_dir("new-uuid", summary_text="New summary")

        # TaskDBManagerをモック化（新しい順にソートされて返される）
        with patch('db.task_db.TaskDBManager') as mock_db_manager:
            mock_instance = MagicMock()
            mock_db_manager.return_value = mock_instance
            # 新しいタスクが最初に来るようにソート済みのリストを返す
            mock_instance.find_completed_tasks_by_key.return_value = [new_task, old_task]

            manager = ContextInheritanceManager(self.base_dir, self.config)
            task_key = GitHubIssueTaskKey("testowner", "testrepo", 123)

            results = manager.find_previous_contexts(task_key)

            self.assertEqual(len(results), 2)
            # 新しいコンテキストが最初
            self.assertEqual(results[0].uuid, "new-uuid")
            self.assertEqual(results[1].uuid, "old-uuid")


class TestPreviousContext(unittest.TestCase):
    """Test PreviousContext dataclass."""

    def test_create_previous_context(self) -> None:
        """PreviousContext作成テスト."""
        prev = PreviousContext(
            uuid="test-uuid",
            task_key_dict={"type": "github_issue"},
            status="completed",
            completed_at=datetime.now(timezone.utc),
            final_summary="Test summary",
            metadata={"key": "value"},
            planning_history=[{"type": "plan"}],
        )

        self.assertEqual(prev.uuid, "test-uuid")
        self.assertEqual(prev.status, "completed")
        self.assertEqual(prev.final_summary, "Test summary")
        self.assertEqual(prev.metadata, {"key": "value"})
        self.assertEqual(len(prev.planning_history), 1)


class TestInheritanceContext(unittest.TestCase):
    """Test InheritanceContext dataclass."""

    def test_create_inheritance_context(self) -> None:
        """InheritanceContext作成テスト."""
        prev = PreviousContext(
            uuid="test-uuid",
            task_key_dict={"type": "github_issue"},
            status="completed",
            completed_at=None,
            final_summary="Summary",
        )
        inheritance = InheritanceContext(
            previous_context=prev,
            final_summary="Summary text",
            planning_summary={"goal": "test"},
        )

        self.assertEqual(inheritance.previous_context.uuid, "test-uuid")
        self.assertEqual(inheritance.final_summary, "Summary text")
        self.assertEqual(inheritance.planning_summary["goal"], "test")


if __name__ == "__main__":
    unittest.main()
