"""実行環境管理モジュール.

Command Executor MCP Server連携のためのDocker実行環境を管理するクラスを提供します。
タスク毎のコンテナ作成・削除、プロジェクトクローン、コマンド実行を担当します。
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


@dataclass
class ContainerInfo:
    """コンテナ情報を保持するデータクラス.
    
    Attributes:
        container_id: DockerコンテナID
        task_uuid: 関連するタスクのUUID
        workspace_path: コンテナ内の作業ディレクトリパス
        created_at: コンテナ作成日時
        status: コンテナの状態

    """

    container_id: str
    task_uuid: str
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

        # Docker設定
        self._docker_config = self._executor_config.get("docker", {})
        self._base_image = self._docker_config.get(
            "base_image",
            os.environ.get("EXECUTOR_BASE_IMAGE", "coding-agent-executor:latest"),
        )

        # リソース制限設定
        resources = self._docker_config.get("resources", {})
        self._cpu_limit = resources.get(
            "cpu_limit",
            int(os.environ.get("EXECUTOR_CPU_LIMIT", "2")),
        )
        self._memory_limit = resources.get(
            "memory_limit",
            os.environ.get("EXECUTOR_MEMORY_LIMIT", "4g"),
        )

        # クローン設定
        clone_config = self._executor_config.get("clone", {})
        self._shallow_clone = clone_config.get("shallow", True)
        self._clone_depth = clone_config.get("depth", 1)
        self._auto_install_deps = clone_config.get("auto_install_deps", True)

        # 実行設定
        execution_config = self._executor_config.get("execution", {})
        self._timeout_seconds = execution_config.get(
            "timeout_seconds",
            int(os.environ.get("EXECUTOR_TIMEOUT", "1800")),
        )
        self._max_output_size = execution_config.get("max_output_size", 1048576)  # 1MB

        # クリーンアップ設定
        cleanup_config = self._executor_config.get("cleanup", {})
        self._cleanup_interval_hours = cleanup_config.get("interval_hours", 24)
        self._stale_threshold_hours = cleanup_config.get("stale_threshold_hours", 24)

        # アクティブコンテナの追跡
        self._active_containers: dict[str, ContainerInfo] = {}

    def is_enabled(self) -> bool:
        """Command Executor機能が有効かどうかを確認する.
        
        Returns:
            有効な場合True、無効な場合False

        """
        # 環境変数による有効/無効チェック
        env_enabled = os.environ.get("COMMAND_EXECUTOR_ENABLED", "").lower()
        if env_enabled:
            return env_enabled == "true"

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

            # 認証トークンの取得
            token = os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN", "")

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

            # 認証トークンの取得
            token = os.environ.get("GITLAB_PERSONAL_ACCESS_TOKEN", "")
            gitlab_url = os.environ.get("GITLAB_API_URL", "https://gitlab.com")

            # APIURLからホスト名を抽出
            host = gitlab_url.replace("https://", "").replace("http://", "").split("/")[0]

            if token:
                clone_url = f"https://oauth2:{token}@{host}/{project_id}.git"
            else:
                clone_url = f"https://{host}/{project_id}.git"

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

    def prepare(self, task: Task) -> ContainerInfo:
        """タスク用のコンテナを作成し、プロジェクトをクローンする.

        Args:
            task: タスクオブジェクト
            
        Returns:
            作成されたコンテナの情報
            
        Raises:
            RuntimeError: コンテナ作成またはクローンに失敗した場合

        """
        task_uuid = task.uuid
        container_name = self._get_container_name(task_uuid)

        self.logger.info("実行環境を準備します: %s", container_name)

        # 既存コンテナがあれば削除
        try:
            self._remove_container(task_uuid)
        except (RuntimeError, subprocess.SubprocessError) as e:
            self.logger.warning("既存コンテナの削除に失敗: %s", e)

        # コンテナを作成
        container_id = self._create_container(task)

        # コンテナ情報を作成
        container_info = ContainerInfo(
            container_id=container_id,
            task_uuid=task_uuid,
            status="created",
        )

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

        # アクティブコンテナに登録
        self._active_containers[task_uuid] = container_info

        self.logger.info("実行環境の準備が完了しました: %s", container_id)
        return container_info

    def _create_container(self, task: Task) -> str:
        """Dockerコンテナを作成する.
        
        Args:
            task: タスクオブジェクト
            
        Returns:
            コンテナID
            
        Raises:
            RuntimeError: コンテナ作成に失敗した場合

        """
        task_uuid = task.uuid
        container_name = self._get_container_name(task_uuid)

        # コンテナ作成コマンドを構築
        create_args = [
            "create",
            "--name", container_name,
            "--cpus", str(self._cpu_limit),
            "--memory", self._memory_limit,
            "--workdir", "/workspace",
            # 非特権モードで実行
            "--security-opt", "no-new-privileges",
            # コンテナを継続実行（sleepコマンド）
            self._base_image,
            "sleep", "infinity",
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

        return container_id

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
        clone_cmd = ["git", "clone"]

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
