"""ExecutionEnvironmentManagerのユニットテスト."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Mock the mcp module before importing
sys.modules["mcp"] = MagicMock()
sys.modules["mcp"].McpError = Exception

from handlers.execution_environment_manager import (
    ContainerInfo,
    ExecutionEnvironmentManager,
    ExecutionResult,
)


class TestContainerInfo(unittest.TestCase):
    """ContainerInfoデータクラスのテスト."""

    def test_container_info_creation(self) -> None:
        """ContainerInfoの作成テスト."""
        info = ContainerInfo(
            container_id="test-container-id",
            task_uuid="test-uuid",
        )
        
        assert info.container_id == "test-container-id"
        assert info.task_uuid == "test-uuid"
        assert info.workspace_path == "/workspace/project"
        assert info.status == "created"

    def test_container_info_with_custom_values(self) -> None:
        """カスタム値でのContainerInfo作成テスト."""
        info = ContainerInfo(
            container_id="custom-container",
            task_uuid="custom-uuid",
            workspace_path="/custom/path",
            status="ready",
        )
        
        assert info.workspace_path == "/custom/path"
        assert info.status == "ready"


class TestExecutionResult(unittest.TestCase):
    """ExecutionResultデータクラスのテスト."""

    def test_execution_result_creation(self) -> None:
        """ExecutionResultの作成テスト."""
        result = ExecutionResult(
            exit_code=0,
            stdout="Hello World",
            stderr="",
            duration_ms=100,
        )
        
        assert result.exit_code == 0
        assert result.stdout == "Hello World"
        assert result.stderr == ""
        assert result.duration_ms == 100

    def test_execution_result_with_error(self) -> None:
        """エラー時のExecutionResult作成テスト."""
        result = ExecutionResult(
            exit_code=1,
            stdout="",
            stderr="Error occurred",
            duration_ms=50,
        )
        
        assert result.exit_code == 1
        assert result.stderr == "Error occurred"


class TestExecutionEnvironmentManager(unittest.TestCase):
    """ExecutionEnvironmentManagerクラスのテスト."""

    def setUp(self) -> None:
        """テスト環境のセットアップ."""
        self.config: dict[str, Any] = {
            "command_executor": {
                "enabled": True,
                "docker": {
                    "base_image": "test-image:latest",
                    "resources": {
                        "cpu_limit": 2,
                        "memory_limit": "4g",
                    },
                },
                "clone": {
                    "shallow": True,
                    "depth": 1,
                    "auto_install_deps": True,
                },
                "execution": {
                    "timeout_seconds": 300,
                    "max_output_size": 1024,
                },
                "cleanup": {
                    "interval_hours": 24,
                    "stale_threshold_hours": 24,
                },
            },
        }
        self.manager = ExecutionEnvironmentManager(self.config)

    def test_manager_creation(self) -> None:
        """ExecutionEnvironmentManagerの作成テスト."""
        assert self.manager is not None
        assert self.manager._base_image == "test-image:latest"
        assert self.manager._cpu_limit == 2
        assert self.manager._memory_limit == "4g"
        assert self.manager._shallow_clone is True
        assert self.manager._clone_depth == 1

    def test_is_enabled_from_config(self) -> None:
        """設定ファイルからの有効/無効判定テスト."""
        assert self.manager.is_enabled() is True
        
        # 無効な設定でテスト
        disabled_config: dict[str, Any] = {
            "command_executor": {"enabled": False}
        }
        disabled_manager = ExecutionEnvironmentManager(disabled_config)
        assert disabled_manager.is_enabled() is False

    @patch.dict("os.environ", {"COMMAND_EXECUTOR_ENABLED": "true"})
    def test_is_enabled_from_env_true(self) -> None:
        """環境変数からの有効判定テスト."""
        manager = ExecutionEnvironmentManager({})
        assert manager.is_enabled() is True

    @patch.dict("os.environ", {"COMMAND_EXECUTOR_ENABLED": "false"})
    def test_is_enabled_from_env_false(self) -> None:
        """環境変数からの無効判定テスト."""
        assert self.manager.is_enabled() is False

    def test_get_container_name(self) -> None:
        """コンテナ名生成テスト."""
        task_uuid = "12345678-1234-1234-1234-123456789abc"
        name = self.manager._get_container_name(task_uuid)
        
        assert name == f"coding-agent-exec-{task_uuid}"
        assert name.startswith(ExecutionEnvironmentManager.CONTAINER_PREFIX)

    def test_get_allowed_commands(self) -> None:
        """許可コマンドリスト取得テスト."""
        commands = self.manager.get_allowed_commands()
        
        # カテゴリが存在することを確認
        assert "build_package" in commands
        assert "test" in commands
        assert "linter_formatter" in commands
        assert "file_operations" in commands
        assert "version_control" in commands
        assert "utilities" in commands
        
        # 主要コマンドが含まれることを確認
        assert "npm" in commands["build_package"]
        assert "pytest" in commands["test"]
        assert "eslint" in commands["linter_formatter"]
        assert "grep" in commands["file_operations"]
        assert "git status" in commands["version_control"]
        assert "echo" in commands["utilities"]

    def test_get_allowed_commands_text(self) -> None:
        """許可コマンドリストテキスト取得テスト."""
        text = self.manager.get_allowed_commands_text()
        
        # カテゴリ名が含まれることを確認
        assert "Build/Package Management" in text
        assert "Test Execution" in text
        assert "Linter/Formatter" in text
        assert "File Operations" in text
        assert "Version Control" in text
        assert "Utilities" in text
        
        # コマンドが含まれることを確認
        assert "npm" in text
        assert "pytest" in text

    @patch("subprocess.run")
    def test_run_docker_command(self, mock_run: MagicMock) -> None:
        """Dockerコマンド実行テスト."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["docker", "ps"],
            returncode=0,
            stdout="container list",
            stderr="",
        )
        
        result = self.manager._run_docker_command(["ps"])

        mock_run.assert_called_once()
        assert result.returncode == 0
        assert result.stdout == "container list"

    @patch("subprocess.run")
    def test_create_container(self, mock_run: MagicMock) -> None:
        """コンテナ作成テスト."""
        # docker create と docker start のモックを設定
        mock_run.side_effect = [
            subprocess.CompletedProcess(
                args=["docker", "create"],
                returncode=0,
                stdout="container-id-123",
                stderr="",
            ),
            subprocess.CompletedProcess(
                args=["docker", "start"],
                returncode=0,
                stdout="",
                stderr="",
            ),
        ]

        # タスクのモックを作成
        mock_task = MagicMock()
        mock_task.uuid = "test-uuid-123"

        container_id, is_custom = self.manager._create_container(mock_task)

        assert container_id == "container-id-123"
        assert is_custom is False  # 環境名指定なしなのでFalse
        assert mock_run.call_count == 2

    @patch("subprocess.run")
    def test_execute_command(self, mock_run: MagicMock) -> None:
        """コマンド実行テスト."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["docker", "exec"],
            returncode=0,
            stdout="command output",
            stderr="",
        )
        
        result = self.manager.execute("container-123", "echo hello")
        
        assert result.exit_code == 0
        assert result.stdout == "command output"
        assert result.stderr == ""
        assert result.duration_ms >= 0

    @patch("subprocess.run")
    def test_execute_command_timeout(self, mock_run: MagicMock) -> None:
        """コマンドタイムアウトテスト."""
        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd=["docker", "exec"],
            timeout=300,
        )
        
        result = self.manager.execute("container-123", "sleep 1000")
        
        assert result.exit_code == -1
        assert "timed out" in result.stderr

    @patch("subprocess.run")
    def test_cleanup(self, mock_run: MagicMock) -> None:
        """クリーンアップテスト."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["docker", "rm"],
            returncode=0,
            stdout="",
            stderr="",
        )
        
        task_uuid = "test-uuid"
        
        # テスト用にアクティブコンテナを追加
        self.manager._active_containers[task_uuid] = ContainerInfo(
            container_id="container-123",
            task_uuid=task_uuid,
        )
        
        self.manager.cleanup(task_uuid)
        
        assert task_uuid not in self.manager._active_containers

    @patch("subprocess.run")
    def test_remove_container_retry(self, mock_run: MagicMock) -> None:
        """コンテナ削除リトライテスト."""
        # 最初は失敗、2回目で成功
        mock_run.side_effect = [
            subprocess.SubprocessError("First attempt failed"),
            subprocess.CompletedProcess(
                args=["docker", "rm"],
                returncode=0,
                stdout="",
                stderr="",
            ),
        ]
        
        # リトライで成功することを確認
        self.manager._remove_container("test-uuid")
        assert mock_run.call_count == 2

    def test_get_container_info(self) -> None:
        """コンテナ情報取得テスト."""
        task_uuid = "test-uuid"
        
        # 存在しない場合
        assert self.manager.get_container_info(task_uuid) is None
        
        # コンテナを追加
        info = ContainerInfo(
            container_id="container-123",
            task_uuid=task_uuid,
        )
        self.manager._active_containers[task_uuid] = info
        
        # 存在する場合
        retrieved = self.manager.get_container_info(task_uuid)
        assert retrieved is not None
        assert retrieved.container_id == "container-123"


class TestParseDatetime(unittest.TestCase):
    """_parse_docker_datetimeメソッドのテスト."""

    def setUp(self) -> None:
        """テスト環境のセットアップ."""
        self.config: dict[str, Any] = {"command_executor": {"enabled": True}}
        self.manager = ExecutionEnvironmentManager(self.config)

    def test_parse_standard_format(self) -> None:
        """Docker標準フォーマットのパーステスト."""
        dt_str = "2024-01-15 12:30:45 +0000 UTC"
        result = self.manager._parse_docker_datetime(dt_str)
        
        assert result is not None
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15
        assert result.hour == 12
        assert result.minute == 30

    def test_parse_iso8601_format(self) -> None:
        """ISO 8601フォーマットのパーステスト."""
        dt_str = "2024-01-15T12:30:45Z"
        result = self.manager._parse_docker_datetime(dt_str)
        
        assert result is not None
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15

    def test_parse_short_format(self) -> None:
        """短縮フォーマットのパーステスト."""
        dt_str = "2024-01-15 12:30:45"
        result = self.manager._parse_docker_datetime(dt_str)
        
        assert result is not None
        assert result.year == 2024
        assert result.month == 1

    def test_parse_invalid_format(self) -> None:
        """無効なフォーマットのパーステスト."""
        dt_str = "invalid-datetime"
        result = self.manager._parse_docker_datetime(dt_str)
        
        assert result is None


class TestGetCloneUrl(unittest.TestCase):
    """_get_clone_urlメソッドのテスト."""

    def setUp(self) -> None:
        """テスト環境のセットアップ."""
        self.config: dict[str, Any] = {"command_executor": {"enabled": True}}
        self.manager = ExecutionEnvironmentManager(self.config)

    def test_github_clone_url_without_token(self) -> None:
        """GitHub URLの生成テスト（トークンなし）."""
        mock_task = MagicMock()
        mock_task_key = MagicMock()
        mock_task_key.owner = "testuser"
        mock_task_key.repo = "testrepo"
        mock_task.get_task_key.return_value = mock_task_key
        mock_task.source_branch = None
        
        with patch.dict("os.environ", {"GITHUB_PERSONAL_ACCESS_TOKEN": ""}):
            url, branch = self.manager._get_clone_url(mock_task)
        
        assert url == "https://github.com/testuser/testrepo.git"
        assert branch is None

    def test_github_clone_url_with_token(self) -> None:
        """GitHub URLの生成テスト（トークンあり）."""
        mock_task = MagicMock()
        mock_task_key = MagicMock()
        mock_task_key.owner = "testuser"
        mock_task_key.repo = "testrepo"
        mock_task.get_task_key.return_value = mock_task_key
        mock_task.source_branch = "feature-branch"
        
        with patch.dict("os.environ", {"GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_token123"}):
            url, branch = self.manager._get_clone_url(mock_task)
        
        assert "x-access-token:ghp_token123@" in url
        assert "github.com/testuser/testrepo.git" in url
        assert branch == "feature-branch"

    def test_gitlab_clone_url(self) -> None:
        """GitLab URLの生成テスト."""
        mock_task = MagicMock()
        # GitLabタスク用のモックを作成（owner/repo属性なし）
        mock_task_key = MagicMock(spec=["project_id"])
        mock_task_key.project_id = "group/project"
        mock_task.get_task_key.return_value = mock_task_key
        mock_task.source_branch = None
        
        # gitlab_client属性がないことを明示的に設定
        mock_task.gitlab_client = None
        
        with patch.dict("os.environ", {
            "GITLAB_PERSONAL_ACCESS_TOKEN": "",
            "GITLAB_API_URL": "https://gitlab.example.com/api/v4",
        }):
            url, branch = self.manager._get_clone_url(mock_task)
        
        assert "gitlab.example.com" in url
        assert "group/project.git" in url


class TestMultiLanguageEnvironment(unittest.TestCase):
    """複数言語環境対応機能のテスト."""

    def setUp(self) -> None:
        """テスト環境のセットアップ."""
        self.config: dict[str, Any] = {
            "command_executor": {
                "enabled": True,
                "environments": {
                    "python": "coding-agent-executor-python:latest",
                    "miniforge": "coding-agent-executor-miniforge:latest",
                    "node": "coding-agent-executor-node:latest",
                    "java": "coding-agent-executor-java:latest",
                    "go": "coding-agent-executor-go:latest",
                },
                "default_environment": "python",
                "docker": {
                    "base_image": "ubuntu:25.04",
                    "resources": {
                        "cpu_limit": 2,
                        "memory_limit": "4g",
                    },
                },
            },
        }
        self.manager = ExecutionEnvironmentManager(self.config)

    def test_get_available_environments(self) -> None:
        """利用可能な環境リスト取得テスト."""
        environments = self.manager.get_available_environments()
        
        # すべての環境が含まれていることを確認
        assert "python" in environments
        assert "miniforge" in environments
        assert "node" in environments
        assert "java" in environments
        assert "go" in environments
        
        # イメージ名が正しいことを確認
        assert environments["python"] == "coding-agent-executor-python:latest"
        assert environments["node"] == "coding-agent-executor-node:latest"

    def test_get_default_environment(self) -> None:
        """デフォルト環境名取得テスト."""
        default_env = self.manager.get_default_environment()
        assert default_env == "python"

    def test_validate_and_select_environment_valid(self) -> None:
        """有効な環境名の検証テスト."""
        # 有効な環境名
        assert self.manager._validate_and_select_environment("python") == "python"
        assert self.manager._validate_and_select_environment("node") == "node"
        assert self.manager._validate_and_select_environment("java") == "java"
        assert self.manager._validate_and_select_environment("go") == "go"
        assert self.manager._validate_and_select_environment("miniforge") == "miniforge"

    def test_validate_and_select_environment_invalid(self) -> None:
        """無効な環境名の検証テスト（デフォルトにフォールバック）."""
        # 無効な環境名はデフォルト環境にフォールバック
        assert self.manager._validate_and_select_environment("invalid") == "python"
        assert self.manager._validate_and_select_environment("ruby") == "python"

    def test_validate_and_select_environment_none(self) -> None:
        """環境名がNoneの場合の検証テスト."""
        # Noneの場合はデフォルト環境
        assert self.manager._validate_and_select_environment(None) == "python"

    @patch("subprocess.run")
    def test_create_container_with_environment(self, mock_run: MagicMock) -> None:
        """環境指定でのコンテナ作成テスト."""
        mock_run.side_effect = [
            subprocess.CompletedProcess(
                args=["docker", "create"],
                returncode=0,
                stdout="container-id-123",
                stderr="",
            ),
            subprocess.CompletedProcess(
                args=["docker", "start"],
                returncode=0,
                stdout="",
                stderr="",
            ),
        ]

        mock_task = MagicMock()
        mock_task.uuid = "test-uuid-123"

        container_id, is_custom = self.manager._create_container(mock_task, "node")

        assert container_id == "container-id-123"
        assert is_custom is True  # 有効な環境名指定なのでTrue

        # docker create コマンドにnode用イメージが含まれることを確認
        create_call = mock_run.call_args_list[0]
        cmd = create_call[0][0]
        assert "coding-agent-executor-node:latest" in cmd

    @patch("subprocess.run")
    def test_create_container_fallback_to_base_image(self, mock_run: MagicMock) -> None:
        """無効な環境名でのbase_imageフォールバックテスト."""
        mock_run.side_effect = [
            subprocess.CompletedProcess(
                args=["docker", "create"],
                returncode=0,
                stdout="container-id-456",
                stderr="",
            ),
            subprocess.CompletedProcess(
                args=["docker", "start"],
                returncode=0,
                stdout="",
                stderr="",
            ),
        ]

        mock_task = MagicMock()
        mock_task.uuid = "test-uuid-456"

        # 無効な環境名を渡す
        container_id, is_custom = self.manager._create_container(mock_task, "invalid_env")

        assert container_id == "container-id-456"
        assert is_custom is False  # 無効な環境名なのでFalse

        # docker create コマンドにbase_imageが含まれることを確認
        create_call = mock_run.call_args_list[0]
        cmd = create_call[0][0]
        assert "ubuntu:25.04" in cmd

    def test_container_info_with_environment_name(self) -> None:
        """環境名を含むContainerInfoの作成テスト."""
        info = ContainerInfo(
            container_id="test-container-id",
            task_uuid="test-uuid",
            environment_name="node",
        )

        assert info.environment_name == "node"
        assert info.container_id == "test-container-id"
        assert info.task_uuid == "test-uuid"

    def test_default_environments_constant(self) -> None:
        """デフォルト環境定数のテスト."""
        from handlers.execution_environment_manager import DEFAULT_ENVIRONMENTS

        # すべての環境が定義されていることを確認
        assert len(DEFAULT_ENVIRONMENTS) == 5
        assert "python" in DEFAULT_ENVIRONMENTS
        assert "miniforge" in DEFAULT_ENVIRONMENTS
        assert "node" in DEFAULT_ENVIRONMENTS
        assert "java" in DEFAULT_ENVIRONMENTS
        assert "go" in DEFAULT_ENVIRONMENTS


if __name__ == "__main__":
    unittest.main()
