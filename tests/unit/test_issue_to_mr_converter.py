"""Issue から MR/PR への変換機能のテスト.

このモジュールは、IssueToMRConverter、BranchNameGenerator、
ContentTransferManager クラスのユニットテストを提供します。
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from handlers.issue_to_mr_converter import (
    MAX_BRANCH_NAME_LENGTH,
    MAX_TRANSFER_COMMENTS,
    RESERVED_BRANCH_NAMES,
    BranchNameGenerator,
    ContentTransferManager,
    ConversionResult,
    IssueToMRConverter,
)


class TestConversionResult:
    """ConversionResult データクラスのテスト."""

    def test_successful_result(self) -> None:
        """成功結果の作成テスト."""
        result = ConversionResult(
            success=True,
            mr_number=123,
            mr_url="https://github.com/owner/repo/pull/123",
            branch_name="feature/codingagent-42-test",
        )
        assert result.success is True
        assert result.mr_number == 123
        assert result.mr_url == "https://github.com/owner/repo/pull/123"
        assert result.branch_name == "feature/codingagent-42-test"
        assert result.error_message is None

    def test_failed_result(self) -> None:
        """失敗結果の作成テスト."""
        result = ConversionResult(
            success=False,
            error_message="Branch creation failed",
        )
        assert result.success is False
        assert result.mr_number is None
        assert result.mr_url is None
        assert result.branch_name is None
        assert result.error_message == "Branch creation failed"


class TestBranchNameGenerator:
    """BranchNameGenerator クラスのテスト."""

    @pytest.fixture
    def mock_llm_client(self) -> MagicMock:
        """モックLLMクライアントを作成する."""
        client = MagicMock()
        client.send_system_prompt = MagicMock()
        client.send_user_message = MagicMock()
        return client

    @pytest.fixture
    def config(self) -> dict:
        """テスト用の設定辞書を返す."""
        return {
            "github": {"bot_name": "test-bot"},
            "gitlab": {"bot_name": "test-bot"},
        }

    @pytest.fixture
    def generator(self, mock_llm_client: MagicMock, config: dict) -> BranchNameGenerator:
        """BranchNameGeneratorインスタンスを作成する."""
        return BranchNameGenerator(mock_llm_client, config)

    def test_sanitize_for_branch(self, generator: BranchNameGenerator) -> None:
        """ブランチ名サニタイズのテスト."""
        assert generator._sanitize_for_branch("Feature Test") == "feature-test"
        assert generator._sanitize_for_branch("fix/bug--fix") == "fix/bug-fix"
        assert generator._sanitize_for_branch("-start-") == "start"
        assert generator._sanitize_for_branch("UPPERCASE") == "uppercase"
        assert generator._sanitize_for_branch("special@#$chars") == "special-chars"

    def test_generate_fallback_name(self, generator: BranchNameGenerator) -> None:
        """フォールバックブランチ名生成のテスト."""
        result = generator._generate_fallback_name("codingagent", 123)
        assert result == "task/codingagent-123-auto-generated"

    def test_validate_and_fix_adds_prefix(self, generator: BranchNameGenerator) -> None:
        """プレフィックスがない場合に追加されることをテスト."""
        result = generator._validate_and_fix(
            "test-branch",
            "codingagent",
            {"number": 123},
            [],
        )
        assert result.startswith("task/")

    def test_validate_and_fix_adds_bot_name(self, generator: BranchNameGenerator) -> None:
        """ボット名が含まれていない場合に追加されることをテスト."""
        result = generator._validate_and_fix(
            "feature/some-feature",
            "codingagent",
            {"number": 123},
            [],
        )
        assert "codingagent" in result.lower()
        assert "123" in result

    def test_validate_and_fix_truncates_long_name(self, generator: BranchNameGenerator) -> None:
        """長すぎるブランチ名が切り詰められることをテスト."""
        long_name = "feature/codingagent-123-" + "a" * 100
        result = generator._validate_and_fix(
            long_name,
            "codingagent",
            {"number": 123},
            [],
        )
        assert len(result) <= MAX_BRANCH_NAME_LENGTH

    def test_validate_and_fix_handles_reserved_names(self, generator: BranchNameGenerator) -> None:
        """予約されたブランチ名が拒否されることをテスト."""
        for reserved in RESERVED_BRANCH_NAMES:
            result = generator._validate_and_fix(
                f"feature/{reserved}",
                "codingagent",
                {"number": 123},
                [],
            )
            # 予約語がbase_nameとして使われないことを確認
            base_name = result.split("/")[-1] if "/" in result else result
            assert base_name.lower() != reserved

    def test_validate_and_fix_handles_duplicates(self, generator: BranchNameGenerator) -> None:
        """重複するブランチ名にサフィックスが追加されることをテスト."""
        existing = ["feature/codingagent-123-test"]
        result = generator._validate_and_fix(
            "feature/codingagent-123-test",
            "codingagent",
            {"number": 123},
            existing,
        )
        # 元のブランチ名と異なることを確認
        assert result not in existing

    def test_generate_with_llm_success(
        self,
        generator: BranchNameGenerator,
        mock_llm_client: MagicMock,
    ) -> None:
        """LLMを使用したブランチ名生成成功テスト."""
        # LLMレスポンスをモック
        llm_response = json.dumps({
            "branch_name": "feature/test-bot-42-add-feature",
            "reasoning": "Test reasoning",
        })
        mock_llm_client.get_response.return_value = (llm_response, [], 100)

        issue_info = {
            "number": 42,
            "title": "Add new feature",
            "body": "Feature description",
            "labels": ["feature"],
        }

        result = generator.generate(issue_info, [])

        assert result is not None
        assert "test-bot" in result or "42" in result
        mock_llm_client.send_system_prompt.assert_called_once()
        mock_llm_client.send_user_message.assert_called_once()

    def test_generate_with_llm_failure_fallback(
        self,
        generator: BranchNameGenerator,
        mock_llm_client: MagicMock,
    ) -> None:
        """LLMエラー時にフォールバックが使用されることをテスト."""
        mock_llm_client.get_response.side_effect = Exception("LLM Error")

        issue_info = {
            "number": 42,
            "title": "Add new feature",
            "body": "Feature description",
        }

        result = generator.generate(issue_info, [])

        assert result is not None
        assert "auto-generated" in result


class TestContentTransferManager:
    """ContentTransferManager クラスのテスト."""

    @pytest.fixture
    def config(self) -> dict:
        """テスト用の設定辞書を返す."""
        return {
            "issue_to_mr_conversion": {
                "exclude_bot_comments": True,
            },
            "github": {"bot_name": "test-bot"},
        }

    @pytest.fixture
    def manager(self, config: dict) -> ContentTransferManager:
        """ContentTransferManagerインスタンスを作成する."""
        return ContentTransferManager(config)

    def test_format_issue_section(self, manager: ContentTransferManager) -> None:
        """Issue情報セクションのフォーマットテスト."""
        issue_info = {
            "number": 123,
            "author": "testuser",
            "created_at": "2025-01-01T12:00:00Z",
            "body": "Issue body content",
        }
        result = manager._format_issue_section(issue_info)

        assert "#123" in result
        assert "@testuser" in result
        assert "2025-01-01T12:00:00Z" in result
        assert "Issue body content" in result

    def test_format_comments_section_empty(self, manager: ContentTransferManager) -> None:
        """空のコメントリストのフォーマットテスト."""
        result = manager._format_comments_section([])
        assert "コメントはありません" in result

    def test_format_comments_section_with_comments(self, manager: ContentTransferManager) -> None:
        """コメントリストのフォーマットテスト."""
        comments = [
            {
                "author": "commenter1",
                "created_at": "2025-01-02T10:00:00Z",
                "body": "First comment",
            },
            {
                "author": "commenter2",
                "created_at": "2025-01-03T15:00:00Z",
                "body": "Second comment",
            },
        ]
        result = manager._format_comments_section(comments)

        assert "@commenter1" in result
        assert "@commenter2" in result
        assert "First comment" in result
        assert "Second comment" in result

    def test_format_comments_section_excludes_bot(self, manager: ContentTransferManager) -> None:
        """ボットコメントが除外されることをテスト."""
        comments = [
            {
                "author": "test-bot",
                "created_at": "2025-01-02T10:00:00Z",
                "body": "Bot comment",
            },
            {
                "author": "human-user",
                "created_at": "2025-01-03T15:00:00Z",
                "body": "Human comment",
            },
        ]
        result = manager._format_comments_section(comments)

        # ボットコメントは除外されるべき
        assert "@test-bot" not in result or "Bot comment" not in result
        assert "Human comment" in result

    def test_format_auto_section(self, manager: ContentTransferManager) -> None:
        """自動生成情報セクションのフォーマットテスト."""
        result = manager._format_auto_section(123)
        assert "Issue #123" in result
        assert "自動生成" in result

    def test_format_mr_body_complete(self, manager: ContentTransferManager) -> None:
        """完全なMR本文生成テスト."""
        issue_info = {
            "number": 123,
            "author": "testuser",
            "created_at": "2025-01-01T12:00:00Z",
            "body": "Issue body",
        }
        comments = [
            {
                "author": "commenter",
                "created_at": "2025-01-02T10:00:00Z",
                "body": "A comment",
            },
        ]
        result = manager.format_mr_body(issue_info, comments)

        assert "📋 元 Issue からの転記" in result
        assert "💬 Issue コメント" in result
        assert "🤖 自動生成情報" in result

    def test_is_bot_comment_detection(self, manager: ContentTransferManager) -> None:
        """ボットコメント検出テスト."""
        assert manager._is_bot_comment("test-bot") is True
        assert manager._is_bot_comment("github-actions") is True
        assert manager._is_bot_comment("ci-bot") is True
        assert manager._is_bot_comment("human-user") is False

    def test_format_comments_respects_max_limit(self, manager: ContentTransferManager) -> None:
        """コメント転記数の上限が守られることをテスト."""
        # MAX_TRANSFER_COMMENTS より多くのコメントを生成
        many_comments = [
            {
                "author": f"user{i}",
                "created_at": f"2025-01-{i:02d}T10:00:00Z",
                "body": f"Comment {i}",
            }
            for i in range(1, MAX_TRANSFER_COMMENTS + 20)
        ]
        result = manager._format_comments_section(many_comments)

        # 最大数以下のコメントのみが含まれているはず
        comment_count = result.count("### コメント")
        assert comment_count <= MAX_TRANSFER_COMMENTS


class TestIssueToMRConverter:
    """IssueToMRConverter クラスのテスト."""

    @pytest.fixture
    def mock_task(self) -> MagicMock:
        """モックタスクを作成する."""
        task = MagicMock()
        task.title = "Test Issue"
        task.body = "Test issue body"
        task.get_user.return_value = "testuser"
        task.labels = ["feature"]
        task.get_comments.return_value = []
        
        # task_keyのモック
        task_key = MagicMock()
        task_key.owner = "test-owner"
        task_key.repo = "test-repo"
        task_key.number = 42
        task.get_task_key.return_value = task_key
        
        return task

    @pytest.fixture
    def mock_llm_client(self) -> MagicMock:
        """モックLLMクライアントを作成する."""
        client = MagicMock()
        client.send_system_prompt = MagicMock()
        client.send_user_message = MagicMock()
        llm_response = json.dumps({
            "branch_name": "feature/codingagent-42-test-issue",
            "reasoning": "Test",
        })
        client.get_response.return_value = (llm_response, [], 100)
        return client

    @pytest.fixture
    def mock_github_client(self) -> MagicMock:
        """モックGitHubクライアントを作成する."""
        client = MagicMock()
        client.list_branches.return_value = []
        client.create_branch.return_value = {}
        client.create_or_update_file.return_value = {"commit": {"sha": "abc123"}}
        client.create_pull_request.return_value = {
            "number": 123,
            "html_url": "https://github.com/owner/repo/pull/123",
        }
        client.update_pull_request.return_value = {}
        client.add_issue_labels.return_value = []
        client.update_issue.return_value = {}
        client.delete_branch.return_value = None
        return client

    @pytest.fixture
    def config(self) -> dict:
        """テスト用の設定辞書を返す."""
        return {
            "github": {
                "bot_label": "coding agent",
                "done_label": "coding agent done",
                "bot_name": "codingagent",
            },
            "issue_to_mr_conversion": {
                "enabled": True,
                "auto_draft": True,
                "exclude_bot_comments": True,
            },
        }

    @pytest.fixture
    def converter(
        self,
        mock_task: MagicMock,
        mock_llm_client: MagicMock,
        mock_github_client: MagicMock,
        config: dict,
    ) -> IssueToMRConverter:
        """IssueToMRConverterインスタンスを作成する."""
        return IssueToMRConverter(
            task=mock_task,
            llm_client=mock_llm_client,
            github_client=mock_github_client,
            config=config,
            platform="github",
        )

    def test_is_enabled_default(self, converter: IssueToMRConverter) -> None:
        """デフォルトで有効であることをテスト."""
        assert converter.is_enabled() is True

    def test_is_enabled_from_env_true(self, converter: IssueToMRConverter) -> None:
        """環境変数による有効化テスト."""
        with patch.dict("os.environ", {"ISSUE_TO_MR_ENABLED": "true"}):
            assert converter.is_enabled() is True

    def test_is_enabled_from_env_false(self, converter: IssueToMRConverter) -> None:
        """環境変数による無効化テスト."""
        with patch.dict("os.environ", {"ISSUE_TO_MR_ENABLED": "false"}):
            assert converter.is_enabled() is False

    def test_is_enabled_from_config_false(
        self,
        mock_task: MagicMock,
        mock_llm_client: MagicMock,
        mock_github_client: MagicMock,
    ) -> None:
        """設定による無効化テスト."""
        config = {
            "issue_to_mr_conversion": {"enabled": False},
            "github": {"bot_name": "codingagent"},
        }
        converter = IssueToMRConverter(
            task=mock_task,
            llm_client=mock_llm_client,
            github_client=mock_github_client,
            config=config,
            platform="github",
        )
        # 環境変数をクリアして設定を使用
        with patch.dict("os.environ", {}, clear=True):
            assert converter.is_enabled() is False

    def test_get_issue_number_github(self, converter: IssueToMRConverter) -> None:
        """GitHub Issue番号取得テスト."""
        assert converter._get_issue_number() == 42

    def test_collect_issue_info(self, converter: IssueToMRConverter) -> None:
        """Issue情報収集テスト."""
        info = converter._collect_issue_info()

        assert info["number"] == 42
        assert info["title"] == "Test Issue"
        assert info["body"] == "Test issue body"
        assert info["author"] == "testuser"
        assert info["owner"] == "test-owner"
        assert info["repo"] == "test-repo"

    def test_convert_when_disabled(
        self,
        mock_task: MagicMock,
        mock_llm_client: MagicMock,
        mock_github_client: MagicMock,
    ) -> None:
        """無効時の変換テスト."""
        config = {
            "issue_to_mr_conversion": {"enabled": False},
            "github": {"bot_name": "codingagent"},
        }
        converter = IssueToMRConverter(
            task=mock_task,
            llm_client=mock_llm_client,
            github_client=mock_github_client,
            config=config,
            platform="github",
        )

        with patch.dict("os.environ", {}, clear=True):
            result = converter.convert()

        assert result.success is False
        assert "disabled" in result.error_message.lower()

    def test_convert_branch_creation_failure(
        self,
        converter: IssueToMRConverter,
        mock_github_client: MagicMock,
    ) -> None:
        """ブランチ作成失敗時のテスト."""
        # list_branches は空リストを返す
        mock_github_client.list_branches.return_value = []
        # create_branch は例外を投げる
        mock_github_client.create_branch.side_effect = Exception("Branch creation failed")

        result = converter.convert()

        assert result.success is False
        assert result.branch_name is None

    def test_convert_successful(
        self,
        converter: IssueToMRConverter,
        mock_github_client: MagicMock,
    ) -> None:
        """変換成功テスト."""
        # GitHub client のモック設定は fixture で済み
        result = converter.convert()

        assert result.success is True
        assert result.mr_number == 123
        assert result.branch_name is not None


class TestGitLabIssueToMRConverter:
    """GitLab向けIssueToMRConverterのテスト."""

    @pytest.fixture
    def mock_task(self) -> MagicMock:
        """GitLab用モックタスクを作成する."""
        task = MagicMock()
        task.title = "Test Issue"
        task.body = "Test issue body"
        task.get_user.return_value = "testuser"
        task.labels = ["feature"]
        task.get_comments.return_value = []
        
        # task_keyのモック（GitLab形式）
        task_key = MagicMock(spec=["project_id", "issue_iid"])
        task_key.project_id = 12345
        task_key.issue_iid = 42
        task.get_task_key.return_value = task_key
        
        return task

    @pytest.fixture
    def mock_llm_client(self) -> MagicMock:
        """モックLLMクライアントを作成する."""
        client = MagicMock()
        client.send_system_prompt = MagicMock()
        client.send_user_message = MagicMock()
        llm_response = json.dumps({
            "branch_name": "feature/codingagent-42-test-issue",
            "reasoning": "Test",
        })
        client.get_response.return_value = (llm_response, [], 100)
        return client

    @pytest.fixture
    def mock_gitlab_client(self) -> MagicMock:
        """モックGitLabクライアントを作成する."""
        client = MagicMock()
        client.list_branches.return_value = []
        client.create_branch.return_value = {}
        client.create_commit.return_value = {"id": "abc123"}
        client.create_merge_request.return_value = {
            "iid": 123,
            "web_url": "https://gitlab.com/project/repo/-/merge_requests/123",
        }
        client.update_merge_request.return_value = {}
        client.delete_branch.return_value = None
        return client

    @pytest.fixture
    def config(self) -> dict:
        """テスト用の設定辞書を返す."""
        return {
            "gitlab": {
                "bot_label": "coding agent",
                "done_label": "coding agent done",
                "bot_name": "codingagent",
            },
            "issue_to_mr_conversion": {
                "enabled": True,
                "auto_draft": True,
            },
        }

    @pytest.fixture
    def converter(
        self,
        mock_task: MagicMock,
        mock_llm_client: MagicMock,
        mock_gitlab_client: MagicMock,
        config: dict,
    ) -> IssueToMRConverter:
        """GitLab用IssueToMRConverterインスタンスを作成する."""
        return IssueToMRConverter(
            task=mock_task,
            llm_client=mock_llm_client,
            gitlab_client=mock_gitlab_client,
            config=config,
            platform="gitlab",
        )

    def test_get_issue_number_gitlab(self, converter: IssueToMRConverter) -> None:
        """GitLab Issue番号取得テスト."""
        assert converter._get_issue_number() == 42

    def test_collect_issue_info_gitlab(self, converter: IssueToMRConverter) -> None:
        """GitLab Issue情報収集テスト."""
        info = converter._collect_issue_info()

        assert info["number"] == 42
        assert info["project_id"] == 12345
        assert info["repository"] == "12345"
