"""実行環境管理モジュール.

Command Executor MCP Server連携のためのDocker実行環境を管理するクラスを提供します。
タスク毎のコンテナ作成・削除、プロジェクトクローン、コマンド実行を担当します。
また、計画フェーズで選択された言語環境に応じた適切なイメージを使用してコンテナを起動します。
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from handlers.task import Task


# デフォルトの利用可能環境定義
DEFAULT_ENVIRONMENTS: dict[str, str] = {
    "python": "coding-agent-executor-python:latest",
    "miniforge": "coding-agent-executor-miniforge:latest",
    "node": "coding-agent-executor-node:latest",
    # Playwright対応環境
    "python-playwright": "coding-agent-executor-python-playwright:latest",
    "node-playwright": "coding-agent-executor-node-playwright:latest",
    "miniforge-playwright": "coding-agent-executor-miniforge-playwright:latest",
}

# デフォルト環境名（フォールバック用定数）
DEFAULT_ENVIRONMENT = "python"


@dataclass
class ContainerInfo:
    """コンテナ情報を保持するデータクラス.
    
    Attributes:
        container_id: DockerコンテナID
        task_uuid: 関連するタスクのUUID
        environment_name: 使用された環境名（python, node等）
        workspace_path: コンテナ内の作業ディレクトリパス
        created_at: コンテナ作成日時
        status: コンテナの状態

    """

    container_id: str
    task_uuid: str
    environment_name: str = DEFAULT_ENVIRONMENT
    workspace_path: str = "/workspace/project"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    status: str = "created"


@dataclass
class ExecutionResult:
    """コマンド実行結果を保持するデータクラス.
    
    Attributes:
        exit_code: コマンドの終了コード
        stdout: 標準出力
        stderr: 標準エラー出力
        duration_ms: 実行時間（ミリ秒）

    """

    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int


class ExecutionEnvironmentManager:
    """タスク毎の実行環境を管理するクラス.
    
    Docker APIを使用してコンテナの作成・削除、プロジェクトのクローン、
    コマンドの実行を行います。
    計画フェーズで選択された言語環境に応じた適切なイメージを使用します。
    """

    # コンテナ名のプレフィックス
    CONTAINER_PREFIX = "coding-agent-exec"

    def __init__(self, config: dict[str, Any]) -> None:
        """ExecutionEnvironmentManagerを初期化する.
        
        Args:
            config: アプリケーション設定辞書

        """
        self.config = config
        self.logger = logging.getLogger(__name__)

        # Command Executor設定を取得
        self._executor_config = config.get("command_executor", {})

        # 利用可能な環境の設定（環境名からイメージ名へのマッピング）
        self._environments: dict[str, str] = self._executor_config.get(
            "environments", DEFAULT_ENVIRONMENTS.copy(),
        )

        # デフォルト環境名（config > デフォルト定数）
        self._default_environment = self._executor_config.get(
            "default_environment", DEFAULT_ENVIRONMENT,
        )

        # Docker設定
        self._docker_config = self._executor_config.get("docker", {})
        self._base_image = self._docker_config.get(
            "base_image", "coding-agent-executor:latest",
        )

        # リソース制限設定
        resources = self._docker_config.get("resources", {})
        self._cpu_limit = resources.get("cpu_limit", 2)
        self._memory_limit = resources.get("memory_limit", "4g")

        # クローン設定
        clone_config = self._executor_config.get("clone", {})
        self._shallow_clone = clone_config.get("shallow", True)
        self._clone_depth = clone_config.get("depth", 1)
        self._auto_install_deps = clone_config.get("auto_install_deps", True)

        # 実行設定
        execution_config = self._executor_config.get("execution", {})
        self._timeout_seconds = execution_config.get("timeout_seconds", 1800)
        self._max_output_size = execution_config.get("max_output_size", 1048576)  # 1MB

        # クリーンアップ設定
        cleanup_config = self._executor_config.get("cleanup", {})
        self._cleanup_interval_hours = cleanup_config.get("interval_hours", 24)
        self._stale_threshold_hours = cleanup_config.get("stale_threshold_hours", 24)

        # アクティブコンテナの追跡
        self._active_containers: dict[str, ContainerInfo] = {}

        # 現在のタスク参照（コマンド実行時に使用）
        self._current_task: Task | None = None

        # テキスト編集MCP設定を取得
        self._text_editor_config = config.get("text_editor_mcp", {})
        self._text_editor_enabled = self._is_text_editor_enabled()

        # アクティブなtext-editor MCPクライアントの追跡
        self._text_editor_clients: dict[str, Any] = {}

        # Playwright MCP設定を取得
        self._playwright_config = config.get("playwright_mcp", {})
        self._playwright_enabled = self._is_playwright_enabled()

        # アクティブなPlaywright MCPクライアントの追跡
        self._playwright_clients: dict[str, Any] = {}

    def get_available_environments(self) -> dict[str, str]:
        """利用可能な環境のリストを取得する.
        
        Returns:
            環境名からイメージ名へのマッピング辞書

        """
        return self._environments.copy()

    def get_default_environment(self) -> str:
        """デフォルト環境名を取得する.
        
        Returns:
            デフォルト環境名

        """
        return self._default_environment

    def set_current_task(self, task: Task) -> None:
        """現在のタスクを設定する.
        
        Args:
            task: 現在処理中のタスク

        """
        self._current_task = task

    def is_enabled(self) -> bool:
        """Command Executor機能が有効かどうかを確認する.
        
        Returns:
            有効な場合True、無効な場合False

        """
        # 設定ファイルによる有効/無効チェック
        return self._executor_config.get("enabled", False)

    def _get_container_name(self, task_uuid: str) -> str:
        """タスクUUIDからコンテナ名を生成する.
        
        Args:
            task_uuid: タスクのUUID
            
        Returns:
            コンテナ名

        """
        return f"{self.CONTAINER_PREFIX}-{task_uuid}"

    def _run_docker_command(
        self,
        args: list[str],
        *,
        timeout: int | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess:
        """Dockerコマンドを実行する.
        
        Args:
            args: Dockerコマンドの引数
            timeout: タイムアウト秒数
            check: エラー時に例外を発生させるかどうか
            
        Returns:
            コマンド実行結果
            
        Raises:
            subprocess.CalledProcessError: コマンド実行エラー
            subprocess.TimeoutExpired: タイムアウト

        """
        cmd = ["docker", *args]
        self.logger.debug("Docker command: %s", " ".join(cmd))

        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout or 60,
            check=check,
        )

    def _get_clone_url(self, task: Task) -> tuple[str, str | None]:
        """タスクからクローンURLとブランチを取得する.
        
        Args:
            task: タスクオブジェクト
            
        Returns:
            (クローンURL, ブランチ名)のタプル

        """
        task_key = task.get_task_key()

        # GitHub の場合
        if hasattr(task_key, "owner") and hasattr(task_key, "repo"):
            owner = task_key.owner
            repo = task_key.repo

            # 認証トークンを設定から取得
            github_config = self.config.get("github", {})
            token = github_config.get("personal_access_token", "")

            if token:
                clone_url = f"https://x-access-token:{token}@github.com/{owner}/{repo}.git"
            else:
                clone_url = f"https://github.com/{owner}/{repo}.git"

            # PRの場合はソースブランチを取得
            branch = getattr(task, "source_branch", None)
            return clone_url, branch

        # GitLab の場合
        if hasattr(task_key, "project_id"):
            project_id = task_key.project_id

            # 認証トークンを設定から取得
            gitlab_config = self.config.get("gitlab", {})
            token = gitlab_config.get("personal_access_token", "")
            gitlab_url = gitlab_config.get("api_url", "https://gitlab.com/api/v4")

            # APIURLからベースURLを抽出（/api/v4を除去）
            base_url = gitlab_url.replace("/api/v4", "").replace("/api/v3", "")

            # プロトコル（http/https）を保持
            if base_url.startswith("https://"):
                protocol = "https://"
                host = base_url.replace("https://", "")
            elif base_url.startswith("http://"):
                protocol = "http://"
                host = base_url.replace("http://", "")
            else:
                protocol = "https://"
                host = base_url

            # GitLabクライアントからプロジェクト情報を取得してパスを使用
            try:
                if hasattr(task, "gitlab_client"):
                    project = task.gitlab_client.get_project(project_id)
                    project_path = project.get("path_with_namespace", str(project_id))
                else:
                    # gitlab_clientがない場合はproject_idをそのまま使用
                    project_path = str(project_id)
            except Exception as e:
                self.logger.warning(
                    "プロジェクトパスの取得に失敗、project_idを使用: %s", e,
                )
                project_path = str(project_id)

            if token:
                clone_url = f"{protocol}oauth2:{token}@{host}/{project_path}.git"
            else:
                clone_url = f"{protocol}{host}/{project_path}.git"

            # MRの場合はソースブランチを取得
            branch = getattr(task, "source_branch", None)
            return clone_url, branch

        # 不明なタスク形式
        error_msg = (
            f"Unknown task type: {type(task_key)}. "
            "Expected GitHub task key with 'owner' and 'repo' attributes, "
            "or GitLab task key with 'project_id' attribute."
        )
        raise ValueError(error_msg)

    def prepare(self, task: Task, environment_name: str | None = None) -> ContainerInfo:
        """タスク用のコンテナを作成し、プロジェクトをクローンする.

        計画フェーズで選択された環境名に基づいて、対応するDockerイメージでコンテナを作成します。
        環境名が指定されない場合や無効な場合は、デフォルト環境を使用します。

        Args:
            task: タスクオブジェクト
            environment_name: 使用する環境名（python, node等）。Noneの場合はデフォルト環境を使用
            
        Returns:
            作成されたコンテナの情報
            
        Raises:
            RuntimeError: コンテナ作成またはクローンに失敗した場合

        """
        task_uuid = task.uuid
        container_name = self._get_container_name(task_uuid)

        # 環境名の検証とイメージ選択
        selected_env = self._validate_and_select_environment(environment_name)

        self.logger.info(
            "実行環境を準備します: %s (環境: %s)", 
            container_name, 
            selected_env,
        )

        # 既存コンテナがあれば削除
        try:
            self._remove_container(task_uuid)
        except (RuntimeError, subprocess.SubprocessError) as e:
            self.logger.warning("既存コンテナの削除に失敗: %s", e)

        # コンテナを作成（選択された環境のイメージを使用）
        container_id, is_custom_image = self._create_container(task, selected_env)

        # コンテナ情報を作成（environment_name属性を含める）
        container_info = ContainerInfo(
            container_id=container_id,
            task_uuid=task_uuid,
            environment_name=selected_env,
            status="created",
        )

        # プレビルドイメージ（coding-agent-executor-*）にはgitが含まれているためスキップ
        # base_imageへフォールバックした場合のみgitをインストール
        if not is_custom_image:
            try:
                self._install_git(container_id)
            except RuntimeError:
                # コンテナを削除してエラーを再送出
                self._remove_container(task_uuid)
                raise

        # プロジェクトをクローン
        try:
            self._clone_project(container_id, task)
            container_info.status = "ready"
        except RuntimeError:
            # コンテナを削除してエラーを再送出
            self._remove_container(task_uuid)
            raise

        # 依存関係の自動インストール
        if self._auto_install_deps:
            try:
                self._install_dependencies(container_id)
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
                self.logger.warning("依存関係のインストールに失敗: %s", e)

        # text-editor MCPサーバーを起動(有効な場合)
        if self._text_editor_enabled:
            try:
                self._start_text_editor_mcp(container_id, task_uuid)
            except Exception as e:
                self.logger.warning("text-editor MCPの起動に失敗しました: %s", e)
                # MCPの起動失敗はワーニングとして記録し、処理は続行

        # Playwright MCPサーバーを起動(Playwright環境の場合)
        if self._playwright_enabled and self.is_playwright_environment(selected_env):
            try:
                self._start_playwright_mcp(container_id, task_uuid)
            except Exception as e:
                self.logger.warning("Playwright MCPの起動に失敗しました: %s", e)
                # MCPの起動失敗はワーニングとして記録し、処理は続行

        # アクティブコンテナに登録
        self._active_containers[task_uuid] = container_info

        self.logger.info(
            "実行環境の準備が完了しました: %s (環境: %s)",
            container_id,
            selected_env,
        )
        return container_info

    def _validate_and_select_environment(self, environment_name: str | None) -> str:
        """環境名を検証し、使用する環境を選択する.

        Args:
            environment_name: 指定された環境名、またはNone

        Returns:
            使用する環境名

        """
        if environment_name is None:
            self.logger.info(
                "環境名が指定されていません。デフォルト環境を使用します: %s",
                self._default_environment,
            )
            return self._default_environment

        if environment_name not in self._environments:
            self.logger.warning(
                "無効な環境名が指定されました: %s。デフォルト環境を使用します: %s",
                environment_name,
                self._default_environment,
            )
            return self._default_environment

        return environment_name

    def _create_container(
        self, task: Task, environment_name: str | None = None,
    ) -> tuple[str, bool]:
        """Dockerコンテナを作成する.

        Args:
            task: タスクオブジェクト
            environment_name: 使用する環境名。指定された場合は対応するイメージを使用

        Returns:
            (コンテナID, カスタムイメージ使用フラグ) のタプル
            カスタムイメージ使用フラグは、environments設定のイメージを使用した場合True

        Raises:
            RuntimeError: コンテナ作成に失敗した場合

        """
        task_uuid = task.uuid
        container_name = self._get_container_name(task_uuid)

        # 環境名に基づいてイメージを選択
        is_custom_image = False
        if environment_name and environment_name in self._environments:
            image = self._environments[environment_name]
            is_custom_image = True
            self.logger.info("環境 '%s' のイメージを使用: %s", environment_name, image)
        else:
            # フォールバック: base_imageを使用
            image = self._base_image
            self.logger.info("デフォルトイメージを使用: %s", image)

        # コンテナ作成コマンドを構築
        create_args = [
            "create",
            "--name", container_name,
            "--cpus", str(self._cpu_limit),
            "--memory", self._memory_limit,
            "--workdir", "/workspace",
            # 非特権モードで実行
            "--security-opt", "no-new-privileges",
            # coding-agent-networkに接続してwebやrabbitmqにアクセス可能にする
            "--network", "coding_agent_coding-agent-network",
            image,
        ]

        try:
            result = self._run_docker_command(create_args)
            container_id = result.stdout.strip()
            self.logger.info("コンテナを作成しました: %s", container_id)
        except subprocess.CalledProcessError as e:
            error_msg = f"コンテナの作成に失敗しました: {e.stderr}"
            self.logger.exception(error_msg)
            raise RuntimeError(error_msg) from e

        # コンテナを起動
        try:
            self._run_docker_command(["start", container_id])
            self.logger.info("コンテナを起動しました: %s", container_id)
        except subprocess.CalledProcessError as e:
            error_msg = f"コンテナの起動に失敗しました: {e.stderr}"
            self.logger.exception(error_msg)
            # 作成したコンテナを削除
            self._run_docker_command(["rm", "-f", container_id], check=False)
            raise RuntimeError(error_msg) from e

        return container_id, is_custom_image

    def _install_git(self, container_id: str) -> None:
        """コンテナ内にgitをインストールする.

        Args:
            container_id: コンテナID

        Raises:
            RuntimeError: インストールに失敗した場合

        """
        self.logger.info("コンテナにgitをインストールします")

        # apt-getでgitをインストール
        install_cmd = [
            "exec",
            container_id,
            "sh",
            "-c",
            "apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*",
        ]

        try:
            self._run_docker_command(install_cmd, timeout=300)
            self.logger.info("gitのインストールが完了しました")
        except subprocess.CalledProcessError as e:
            error_msg = f"gitのインストールに失敗しました: {e.stderr}"
            self.logger.exception(error_msg)
            raise RuntimeError(error_msg) from e
        except subprocess.TimeoutExpired as e:
            error_msg = "gitのインストールがタイムアウトしました"
            self.logger.exception(error_msg)
            raise RuntimeError(error_msg) from e

    def _clone_project(self, container_id: str, task: Task) -> None:
        """コンテナ内にプロジェクトをクローンする.

        Args:
            container_id: コンテナID
            task: タスクオブジェクト

        Raises:
            RuntimeError: クローンに失敗した場合

        """
        clone_url, branch = self._get_clone_url(task)

        # URLから認証情報を除去してログ出力
        safe_url = re.sub(r"://[^@]+@", "://***@", clone_url)
        self.logger.info("プロジェクトをクローンします: %s", safe_url)

        # クローンコマンドを構築
        clone_cmd = [
            "git",
            "-c", "http.sslVerify=false",  # SSL検証を無効化（セルフホストGitLab用）
            "clone",
        ]

        if self._shallow_clone:
            clone_cmd.extend(["--depth", str(self._clone_depth)])

        if branch:
            clone_cmd.extend(["--branch", branch])

        clone_cmd.extend([clone_url, "/workspace/project"])

        # コンテナ内でクローン実行
        exec_args = ["exec", container_id, *clone_cmd]

        try:
            self._run_docker_command(exec_args, timeout=300)
            self.logger.info("プロジェクトのクローンが完了しました")
        except subprocess.CalledProcessError as e:
            # 認証情報を除去してエラーログを出力
            safe_stderr = re.sub(r"://[^@]+@", "://***@", e.stderr)
            error_msg = f"プロジェクトのクローンに失敗しました: {safe_stderr}"
            self.logger.exception(error_msg)
            raise RuntimeError(error_msg) from e
        except subprocess.TimeoutExpired as e:
            error_msg = "プロジェクトのクローンがタイムアウトしました"
            self.logger.exception(error_msg)
            raise RuntimeError(error_msg) from e

    def _install_dependencies(self, container_id: str) -> None:
        """プロジェクトの依存関係をインストールする.

        プロジェクトの種類を自動検出し、適切なパッケージマネージャーで
        依存関係をインストールします。

        Args:
            container_id: コンテナID

        """
        self.logger.info("依存関係のインストールを開始します")

        # 依存関係ファイルの検出とインストールコマンドのマッピング
        dep_checks = [
            # (ファイル名, インストールコマンド)
            ("package.json", ["npm", "install"]),
            ("requirements.txt", ["pip", "install", "-r", "requirements.txt"]),
            ("environment.yml", ["mamba", "env", "update", "-f", "environment.yml"]),
            ("condaenv.yaml", ["mamba", "env", "update", "-f", "condaenv.yaml"]),
            ("go.mod", ["go", "mod", "download"]),
            ("pom.xml", ["mvn", "dependency:resolve", "-q"]),
            ("Gemfile", ["bundle", "install"]),
        ]

        workspace = "/workspace/project"

        for dep_file, install_cmd in dep_checks:
            # ファイルの存在確認
            check_args = ["exec", container_id, "test", "-f", f"{workspace}/{dep_file}"]
            result = self._run_docker_command(check_args, check=False)

            if result.returncode == 0:
                self.logger.info("依存関係ファイルを検出: %s", dep_file)

                # インストールコマンドを実行
                exec_args = ["exec", "-w", workspace, container_id, *install_cmd]
                try:
                    self._run_docker_command(exec_args, timeout=600)
                    self.logger.info("依存関係のインストールが完了: %s", dep_file)
                except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
                    self.logger.warning("依存関係のインストールに失敗: %s - %s", dep_file, e)

    def execute(self, container_id: str, command: str) -> ExecutionResult:
        """指定コンテナでコマンドを実行する.
        
        Args:
            container_id: コンテナID
            command: 実行するコマンド
            
        Returns:
            コマンド実行結果

        """
        self.logger.info("コマンドを実行します: %s", command)

        start_time = time.time()

        # コンテナ内でコマンドを実行
        exec_args = ["exec", "-w", "/workspace/project", container_id, "sh", "-c", command]

        try:
            result = self._run_docker_command(
                exec_args,
                timeout=self._timeout_seconds,
                check=False,
            )

            duration_ms = int((time.time() - start_time) * 1000)

            # 出力サイズの制限
            stdout = result.stdout[:self._max_output_size]
            stderr = result.stderr[:self._max_output_size]

            execution_result = ExecutionResult(
                exit_code=result.returncode,
                stdout=stdout,
                stderr=stderr,
                duration_ms=duration_ms,
            )

            self.logger.info(
                "コマンド実行完了: exit_code=%d, duration=%dms",
                execution_result.exit_code,
                execution_result.duration_ms,
            )

            return execution_result

        except subprocess.TimeoutExpired:
            duration_ms = int((time.time() - start_time) * 1000)
            self.logger.warning("コマンドがタイムアウトしました: %s", command)

            return ExecutionResult(
                exit_code=-1,
                stdout="",
                stderr=f"Command timed out after {self._timeout_seconds} seconds",
                duration_ms=duration_ms,
            )

    def cleanup(self, task_uuid: str) -> None:
        """タスク終了時にコンテナを削除する.

        Args:
            task_uuid: タスクのUUID

        """
        self.logger.info("実行環境をクリーンアップします: %s", task_uuid)

        # text-editor MCPサーバーを停止(有効な場合)
        self._stop_text_editor_mcp(task_uuid)

        # Playwright MCPサーバーを停止(有効な場合)
        self._stop_playwright_mcp(task_uuid)

        try:
            self._remove_container(task_uuid)
            # アクティブコンテナから削除
            self._active_containers.pop(task_uuid, None)
            self.logger.info("実行環境のクリーンアップが完了しました: %s", task_uuid)
        except (RuntimeError, subprocess.SubprocessError) as e:
            self.logger.exception("実行環境のクリーンアップに失敗: %s", e)

    def _remove_container(self, task_uuid: str) -> None:
        """コンテナを削除する.

        Args:
            task_uuid: タスクのUUID

        Raises:
            RuntimeError: 削除に失敗した場合(3回リトライ後)

        """
        container_name = self._get_container_name(task_uuid)

        # 最大3回リトライ
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # コンテナを強制削除
                self._run_docker_command(["rm", "-f", container_name], check=False)
                self.logger.info("コンテナを削除しました: %s", container_name)
                return
            except subprocess.SubprocessError as e:
                self.logger.warning(
                    "コンテナ削除に失敗 (試行 %d/%d): %s",
                    attempt + 1, max_retries, e,
                )
                if attempt < max_retries - 1:
                    time.sleep(1)

        error_msg = f"コンテナの削除に失敗しました: {container_name}"
        raise RuntimeError(error_msg)

    def cleanup_stale_containers(self) -> int:
        """残存コンテナを定期的にクリーンアップする.

        命名規則に合致し、一定時間経過したコンテナを削除します。
        
        Returns:
            削除されたコンテナ数

        """
        self.logger.info("残存コンテナのクリーンアップを開始します")

        # コンテナ一覧を取得
        list_args = [
            "ps", "-a",
            "--filter", f"name={self.CONTAINER_PREFIX}",
            "--format", "{{.ID}}\t{{.Names}}\t{{.CreatedAt}}",
        ]

        try:
            result = self._run_docker_command(list_args, check=False)
        except subprocess.SubprocessError as e:
            self.logger.exception("コンテナ一覧の取得に失敗: %s", e)
            return 0

        if not result.stdout.strip():
            self.logger.info("残存コンテナはありません")
            return 0

        deleted_count = 0
        threshold = datetime.now(timezone.utc)

        for line in result.stdout.strip().split("\n"):
            if not line:
                continue

            parts = line.split("\t")
            if len(parts) < 3:
                continue

            container_id, container_name, created_at = parts[0], parts[1], parts[2]

            # 作成時刻をパース（複数のフォーマットに対応）
            created = self._parse_docker_datetime(created_at)
            if created is None:
                self.logger.warning("コンテナ作成時刻のパースに失敗: %s", created_at)
                continue

            # 閾値時間を超過しているか確認
            hours_diff = (threshold - created).total_seconds() / 3600
            if hours_diff > self._stale_threshold_hours:
                self.logger.info(
                    "残存コンテナを削除します: %s (経過時間: %.1f時間)",
                    container_name, hours_diff,
                )
                self._run_docker_command(["rm", "-f", container_id], check=False)
                deleted_count += 1

        self.logger.info("残存コンテナのクリーンアップが完了: %d件削除", deleted_count)
        return deleted_count

    def _parse_docker_datetime(self, datetime_str: str) -> datetime | None:
        """Docker日時文字列をパースする.

        複数のDockerバージョンで異なる日時フォーマットに対応します。

        Args:
            datetime_str: Docker日時文字列

        Returns:
            パースされたdatetime、失敗時はNone

        """
        # 試行するフォーマットのリスト
        formats = [
            # Docker標準: "2024-01-01 12:00:00 +0000 UTC"
            ("%Y-%m-%d %H:%M:%S", lambda s: s.split(" +")[0]),
            # ISO 8601風: "2024-01-01T12:00:00Z"
            ("%Y-%m-%dT%H:%M:%SZ", lambda s: s),
            # 短縮形: "2024-01-01 12:00:00"
            ("%Y-%m-%d %H:%M:%S", lambda s: s.split(" ")[0] + " " + s.split(" ")[1] if " " in s else s),
        ]

        for fmt, preprocessor in formats:
            try:
                processed = preprocessor(datetime_str)
                return datetime.strptime(processed, fmt).replace(tzinfo=timezone.utc)
            except (ValueError, IndexError):
                continue

        return None

    def get_container_info(self, task_uuid: str) -> ContainerInfo | None:
        """タスクUUIDからコンテナ情報を取得する.
        
        Args:
            task_uuid: タスクのUUID
            
        Returns:
            コンテナ情報、存在しない場合はNone

        """
        return self._active_containers.get(task_uuid)

    def get_allowed_commands(self) -> dict[str, list[str]]:
        """許可コマンドリストを取得する.
        
        Returns:
            カテゴリ別の許可コマンドリスト

        """
        return {
            "build_package": [
                "npm", "yarn", "pnpm", "pip", "pip3", "conda", "mamba",
                "python", "python3", "go", "cargo", "maven", "mvn", "gradle",
                "make", "cmake", "bundle", "gem", "composer", "dotnet",
            ],
            "test": [
                "pytest", "jest", "mocha", "rspec", "phpunit",
                "go test", "cargo test", "dotnet test",
            ],
            "linter_formatter": [
                "eslint", "prettier", "black", "flake8", "pylint", "mypy",
                "rubocop", "gofmt", "golint", "rustfmt", "clippy", "tsc",
            ],
            "file_operations": [
                "ls", "cat", "head", "tail", "grep", "find", "wc",
                "diff", "tree", "file", "stat",
            ],
            "version_control": [
                "git status", "git diff", "git log", "git branch",
                "git show", "git blame",
            ],
            "utilities": [
                "echo", "pwd", "cd", "mkdir", "rm", "cp", "mv", "touch",
                "chmod", "env", "which", "curl", "wget", "tar", "unzip",
                "jq", "sed", "awk", "sort", "uniq", "xargs",
            ],
        }

    def get_allowed_commands_text(self) -> str:
        """許可コマンドリストをテキスト形式で取得する.
        
        システムプロンプト埋め込み用のフォーマットで返します。
        
        Returns:
            カテゴリ別の許可コマンドリスト（テキスト形式）

        """
        commands = self.get_allowed_commands()

        lines = []
        category_names = {
            "build_package": "Build/Package Management",
            "test": "Test Execution",
            "linter_formatter": "Linter/Formatter",
            "file_operations": "File Operations",
            "version_control": "Version Control",
            "utilities": "Utilities",
        }

        for category, cmd_list in commands.items():
            category_name = category_names.get(category, category)
            lines.append(f"{category_name}: {', '.join(cmd_list)}")

        return "\n".join(lines)

    def execute_command(self, command: str, working_directory: str | None = None) -> dict[str, Any]:
        """実行環境コンテナ内でコマンドを実行する.
        
        Args:
            command: 実行するコマンド
            working_directory: 作業ディレクトリ（Noneの場合はデフォルト）
            
        Returns:
            実行結果の辞書 {"exit_code": int, "stdout": str, "stderr": str, "duration_ms": int}
            
        Raises:
            RuntimeError: 実行環境が準備されていない場合

        """
        if self._current_task is None:
            raise RuntimeError("Current task not set. Call set_current_task() first.")

        task_uuid = self._current_task.uuid
        container_info = self._active_containers.get(task_uuid)

        if container_info is None or container_info.status != "ready":
            raise RuntimeError(f"Execution environment not ready for task {task_uuid}")

        container_id = container_info.container_id
        work_dir = working_directory or container_info.workspace_path

        self.logger.info("コマンドを実行します: %s (作業ディレクトリ: %s)", command, work_dir)

        # コマンド実行
        exec_args = [
            "exec",
            "-w", work_dir,
            container_id,
            "sh", "-c", command,
        ]

        start_time = time.time()

        try:
            result = self._run_docker_command(
                exec_args,
                timeout=self._timeout_seconds,
                check=False,
            )
            duration_ms = int((time.time() - start_time) * 1000)

            # 出力サイズを制限
            stdout = result.stdout
            stderr = result.stderr

            if len(stdout) > self._max_output_size:
                stdout = stdout[:self._max_output_size] + "\n...(truncated)"
            if len(stderr) > self._max_output_size:
                stderr = stderr[:self._max_output_size] + "\n...(truncated)"

            return {
                "exit_code": result.returncode,
                "stdout": stdout,
                "stderr": stderr,
                "duration_ms": duration_ms,
            }

        except subprocess.TimeoutExpired:
            duration_ms = int((time.time() - start_time) * 1000)
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": f"Command timeout after {self._timeout_seconds} seconds",
                "duration_ms": duration_ms,
            }
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": f"Command execution error: {str(e)}",
                "duration_ms": duration_ms,
            }

    def get_function_calling_functions(self) -> list[dict[str, Any]]:
        """Function calling用の関数定義を取得する.
        
        Returns:
            関数定義のリスト

        """
        if not self.is_enabled():
            return []

        return [
            {
                "name": "command-executor_execute_command",
                "description": "Execute a command in an isolated Docker execution environment with project source code. The project is already cloned and dependencies are installed.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "The command to execute (e.g., 'pytest tests/', 'npm test', 'grep -rn \"function_name\" src/')",
                        },
                        "working_directory": {
                            "type": "string",
                            "description": "Working directory path (optional, defaults to project root /workspace/project)",
                        },
                    },
                    "required": ["command"],
                },
            },
        ]

    def get_function_calling_tools(self) -> list[dict[str, Any]]:
        """Function calling用のツール定義を取得する（OpenAI形式）.
        
        Returns:
            ツール定義のリスト

        """
        if not self.is_enabled():
            return []

        functions = self.get_function_calling_functions()
        return [
            {
                "type": "function",
                "function": func,
            }
            for func in functions
        ]

    # ==========================================================================
    # テキスト編集MCP関連メソッド
    # ==========================================================================

    def _is_text_editor_enabled(self) -> bool:
        """テキスト編集MCP機能が有効かどうかを確認する.
        
        Returns:
            有効な場合True、無効な場合False
        """
        # 設定ファイルによる有効/無効チェック
        return self._text_editor_config.get("enabled", True)

    def is_text_editor_enabled(self) -> bool:
        """テキスト編集MCP機能が有効かどうかを外部から確認する.
        
        Returns:
            有効な場合True、無効な場合False
        """
        return self._text_editor_enabled

    def _start_text_editor_mcp(self, container_id: str, task_uuid: str) -> None:
        """コンテナ内でtext-editor MCPサーバーを起動する.
        
        Args:
            container_id: DockerコンテナID
            task_uuid: タスクのUUID
            
        Raises:
            RuntimeError: MCPサーバーの起動に失敗した場合
        """
        if not self._text_editor_enabled:
            return

        from clients.text_editor_mcp_client import TextEditorMCPClient

        self.logger.info("text-editor MCPサーバーを起動します: %s", task_uuid)

        try:
            client = TextEditorMCPClient(
                container_id=container_id,
                workspace_path="/workspace/project",
                timeout_seconds=self._timeout_seconds,
            )
            client.start()
            self._text_editor_clients[task_uuid] = client
            self.logger.info("text-editor MCPサーバーが起動しました: %s", task_uuid)
        except Exception as e:
            self.logger.exception("text-editor MCPサーバーの起動に失敗しました: %s", e)
            raise RuntimeError(f"Failed to start text-editor MCP: {e}") from e

    def _stop_text_editor_mcp(self, task_uuid: str) -> None:
        """text-editor MCPサーバーを停止する.
        
        Args:
            task_uuid: タスクのUUID
        """
        client = self._text_editor_clients.pop(task_uuid, None)
        if client is not None:
            try:
                client.stop()
                self.logger.info("text-editor MCPサーバーを停止しました: %s", task_uuid)
            except Exception as e:
                self.logger.warning("text-editor MCPサーバーの停止に失敗しました: %s", e)

    def call_text_editor_tool(
        self,
        tool: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """text-editorツールを呼び出す.
        
        Args:
            tool: ツール名（"text_editor"固定）
            arguments: コマンドの引数
            
        Returns:
            実行結果の辞書 {"success": bool, "content": str, "error": str}
            
        Raises:
            RuntimeError: 現在のタスクが設定されていない場合、
                         またはtext-editor MCPが有効でない場合
        """
        if self._current_task is None:
            raise RuntimeError("Current task not set. Call set_current_task() first.")

        task_uuid = self._current_task.uuid
        client = self._text_editor_clients.get(task_uuid)

        if client is None:
            raise RuntimeError(f"Text editor MCP not started for task {task_uuid}")

        # Noneの値を持つキーを削除
        cleaned_arguments = {k: v for k, v in arguments.items() if v is not None}

        self.logger.info("text_editorツールを呼び出します: %s", cleaned_arguments)

        try:
            result = client.call_tool(tool, cleaned_arguments)
            return {
                "success": result.success,
                "content": result.content,
                "error": result.error,
            }
        except Exception as e:
            self.logger.exception("text_editorツール呼び出し中にエラー発生: %s", e)
            return {
                "success": False,
                "content": "",
                "error": str(e),
            }

    def get_text_editor_client(self, task_uuid: str) -> Any | None:
        """タスクのtext-editor MCPクライアントを取得する.
        
        Args:
            task_uuid: タスクのUUID
            
        Returns:
            TextEditorMCPClientインスタンス、存在しない場合はNone
        """
        return self._text_editor_clients.get(task_uuid)

    def get_text_editor_functions(self) -> list[dict[str, Any]]:
        """text-editorツールのFunction calling用関数定義を取得する.
        
        Returns:
            関数定義のリスト
        """
        if not self._text_editor_enabled:
            return []

        return [
            {
                "name": "text_editor",
                "description": (
                    "A text editor tool for viewing, creating, and editing files in the project workspace. "
                    "Supports multiple commands specified via the 'command' parameter:\n"
                    "- view: View file contents or list directory contents\n"
                    "- create: Create a new file with specified content\n"
                    "- str_replace: Replace a specific string in a file (must match exactly one location)\n"
                    "- insert: Insert new text at a specific line number\n"
                    "- undo_edit: Revert the most recent edit to a file"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "enum": ["view", "create", "str_replace", "insert", "undo_edit"],
                            "description": "The command to execute",
                        },
                        "path": {
                            "type": "string",
                            "description": "File or directory path (required for all commands)",
                        },
                        "view_range": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "Optional line range [start, end] for 'view' command on files. Omit if not needed.",
                        },
                        "file_text": {
                            "type": "string",
                            "description": "File content (required for 'create' command)",
                        },
                        "old_str": {
                            "type": "string",
                            "description": "String to replace (required for 'str_replace' command)",
                        },
                        "new_str": {
                            "type": "string",
                            "description": "Replacement string (required for 'str_replace' and 'insert' commands)",
                        },
                        "insert_line": {
                            "type": "integer",
                            "description": "Line number to insert at (required for 'insert' command)",
                        },
                    },
                    "required": ["command", "path"],
                },
            },
        ]

    def get_text_editor_tools(self) -> list[dict[str, Any]]:
        """text-editorツールのFunction calling用ツール定義を取得する(OpenAI形式).
        
        Returns:
            ツール定義のリスト
        """
        if not self._text_editor_enabled:
            return []

        functions = self.get_text_editor_functions()
        return [
            {
                "type": "function",
                "function": func,
            }
            for func in functions
        ]

    # ==== Playwright MCP関連メソッド ====

    def _is_playwright_enabled(self) -> bool:
        """Playwright MCP機能が有効かどうかを確認する.
        
        Returns:
            有効な場合True、無効な場合False
        """
        return self._playwright_config.get("enabled", True)

    def is_playwright_enabled(self) -> bool:
        """Playwright MCP機能が有効かどうかを確認する（外部から呼び出し可能）.
        
        Returns:
            有効な場合True、無効な場合False
        """
        return self._playwright_enabled

    def is_playwright_environment(self, env_name: str) -> bool:
        """環境名がPlaywright対応かをチェックする.
        
        Args:
            env_name: 環境名
            
        Returns:
            Playwright対応環境の場合True
        """
        return "-playwright" in env_name

    def _start_playwright_mcp(self, container_id: str, task_uuid: str) -> None:
        """Playwright MCPサーバーを起動する.
        
        Args:
            container_id: DockerコンテナID
            task_uuid: タスクのUUID
            
        Raises:
            RuntimeError: サーバー起動に失敗した場合
        """
        if not self._playwright_enabled:
            return

        from clients.playwright_mcp_client import PlaywrightMCPClient

        try:
            self.logger.info("Playwright MCPサーバーを起動します: %s", task_uuid)
            
            client = PlaywrightMCPClient(
                container_id=container_id,
                workspace_path="/workspace/project",
                timeout_seconds=30,
            )
            client.start()
            
            self._playwright_clients[task_uuid] = client
            self.logger.info("Playwright MCPサーバーが起動しました: %s", task_uuid)
            
        except Exception as e:
            self.logger.exception("Playwright MCPサーバーの起動に失敗しました")
            msg = f"Failed to start Playwright MCP server: {e}"
            raise RuntimeError(msg) from e

    def _stop_playwright_mcp(self, task_uuid: str) -> None:
        """Playwright MCPサーバーを停止する.
        
        Args:
            task_uuid: タスクのUUID
        """
        client = self._playwright_clients.pop(task_uuid, None)
        if client:
            try:
                client.stop()
                self.logger.info("Playwright MCPサーバーを停止しました: %s", task_uuid)
            except Exception as e:
                self.logger.warning("Playwright MCPサーバー停止中にエラー発生: %s", e)

    def call_playwright_tool(
        self,
        task_uuid: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Playwrightツールを呼び出す.
        
        Args:
            task_uuid: タスクのUUID
            tool_name: ツール名（playwright_navigate等）
            arguments: ツールの引数
            
        Returns:
            ツール実行結果
        """
        client = self._playwright_clients.get(task_uuid)
        if not client:
            msg = f"Playwright MCP client not found for task: {task_uuid}"
            self.logger.error(msg)
            return {"error": msg}

        self.logger.info("Playwrightツールを呼び出します: %s, args: %s", tool_name, arguments)
        
        try:
            result = client.call_tool(tool_name, arguments)
            
            if result.success:
                return {"success": True, "content": result.content}
            else:
                return {"success": False, "error": result.error}
                
        except Exception as e:
            self.logger.exception("Playwrightツール呼び出し中にエラー発生: %s", e)
            return {"success": False, "error": str(e)}

    def get_playwright_client(self, task_uuid: str) -> Any | None:
        """Playwright MCP Clientを取得する.
        
        Args:
            task_uuid: タスクのUUID
            
        Returns:
            Playwright MCP Client、存在しない場合None
        """
        return self._playwright_clients.get(task_uuid)

    def get_playwright_functions(self) -> list[dict[str, Any]]:
        """PlaywrightツールのFunction calling用関数定義を取得する.
        
        Returns:
            関数定義のリスト
        """
        if not self._playwright_enabled:
            return []

        # Playwright MCPクライアントから関数定義を取得
        # 実際のクライアントインスタンスがなくても定義は取得可能
        from clients.playwright_mcp_client import PlaywrightMCPClient

        # 一時インスタンスを作成して関数定義を取得
        # container_idは定義取得には不要なのでダミー値を使用
        temp_client = PlaywrightMCPClient(
            container_id="dummy",
            workspace_path="/workspace/project",
        )
        return temp_client.get_function_calling_functions()

    def get_playwright_tools(self) -> list[dict[str, Any]]:
        """PlaywrightツールのFunction calling用ツール定義を取得する(OpenAI形式).
        
        Returns:
            ツール定義のリスト
        """
        if not self._playwright_enabled:
            return []

        functions = self.get_playwright_functions()
        return [
            {
                "type": "function",
                "function": func,
            }
            for func in functions
        ]


