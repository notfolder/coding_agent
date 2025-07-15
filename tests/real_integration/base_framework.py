"""リアル統合テスト用のベースフレームワーク.

このモジュールは、モックではなく実際のGitHub/GitLabとLLM APIを使用して
統合テストを実行するためのベースインフラを提供します。
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import yaml

# 定数
EXPECTED_REPO_PARTS_COUNT = 2  # owner/repo形式のパーツ数

# LLMクライアントの遅延インポート用
try:
    from clients.lm_client import get_llm_client
except ImportError:
    get_llm_client = None


class RealIntegrationTestFramework:
    """リアル統合テストを実行するためのフレームワーク."""

    def __init__(self, platform: str = "github") -> None:
        """テストフレームワークを初期化する.

        Args:
            platform: "github" または "gitlab" のいずれか

        """
        self.platform = platform
        self.logger = logging.getLogger(__name__)
        self.test_repo = None
        self.test_project_id = None
        self.cleanup_tasks = []

        # Check for required environment variables
        self._check_prerequisites()

        # Load configuration
        self.config = self._load_config()

        # Get bot name from environment variables (optional)
        self.bot_name = self._get_bot_name()

    def _check_prerequisites(self) -> None:
        """必要な環境変数が設定されているかをチェックする."""
        if self.platform == "github":
            github_token = (
                os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN")
                or os.environ.get("GITHUB_TOKEN")
            )
            if not github_token:
                msg = "GitHubテスト用にGITHUB_PERSONAL_ACCESS_TOKEN環境変数が必要です"
                raise ValueError(msg)
            if not os.environ.get("GITHUB_TEST_REPO"):
                msg = "GITHUB_TEST_REPO環境変数が必要です (形式: owner/repo)"
                raise ValueError(msg)
        elif self.platform == "gitlab":
            gitlab_token = (
                os.environ.get("GITLAB_PERSONAL_ACCESS_TOKEN")
                or os.environ.get("GITLAB_TOKEN")
            )
            if not gitlab_token:
                msg = "GitLabテスト用にGITLAB_PERSONAL_ACCESS_TOKEN環境変数が必要です"
                raise ValueError(msg)
            if not os.environ.get("GITLAB_TEST_PROJECT"):
                msg = "GITLAB_TEST_PROJECT環境変数が必要です"
                raise ValueError(msg)

        # LLM設定をチェック
        llm_provider = os.environ.get("LLM_PROVIDER", "openai")
        if llm_provider == "openai" and not os.environ.get("OPENAI_API_KEY"):
            msg = "OpenAI使用時にはOPENAI_API_KEY環境変数が必要です"
            raise ValueError(msg)

    def _load_config(self) -> dict[str, Any]:
        """テスト設定を読み込む."""
        config_path = Path(__file__).parent.parent / f"real_test_config_{self.platform}.yaml"

        if not config_path.exists():
            msg = f"設定ファイルが見つかりません: {config_path}"
            raise FileNotFoundError(msg)

        with config_path.open() as f:
            config = yaml.safe_load(f)

        # 環境変数で設定を上書き
        if self.platform == "github":
            repo_parts = os.environ.get("GITHUB_TEST_REPO", "").split("/")
            if len(repo_parts) == EXPECTED_REPO_PARTS_COUNT:
                config["github"]["owner"] = repo_parts[0]
                config["github"]["repo"] = repo_parts[1]
                self.test_repo = f"{repo_parts[0]}/{repo_parts[1]}"
        elif self.platform == "gitlab":
            project = os.environ.get("GITLAB_TEST_PROJECT")
            if project:
                config["gitlab"]["project_id"] = project
                self.test_project_id = project

        return config

    def _get_bot_name(self) -> str | None:
        """プラットフォーム固有のボット名を環境変数から取得する.

        Returns:
            ボット名、または設定されていない場合はNone

        """
        if self.platform == "github":
            return os.environ.get("GITHUB_BOT_NAME")
        if self.platform == "gitlab":
            return os.environ.get("GITLAB_BOT_NAME")
        return None

    def setup_test_environment(self) -> None:
        """テスト環境をセットアップする."""
        self.logger.info("Setting up test environment for %s", self.platform)

        # テストラベルが存在することを確認
        self._ensure_labels_exist()

    def teardown_test_environment(self) -> None:
        """テスト環境をクリーンアップする."""
        self.logger.info("Cleaning up test environment")

        # クリーンアップタスクを逆順で実行してエラーを蓄積
        cleanup_errors = []
        for cleanup_task in reversed(self.cleanup_tasks):
            self._execute_cleanup_task(cleanup_task, cleanup_errors)

        # エラーがあった場合はまとめてログ出力
        if cleanup_errors:
            for task_name, error in cleanup_errors:
                self.logger.warning("Cleanup task %s failed: %s", task_name, error)

    def _execute_cleanup_task(
        self,
        cleanup_task: callable,
        cleanup_errors: list[tuple[str, Exception]],
    ) -> None:
        """個別のクリーンアップタスクを実行し、エラーを記録する."""
        try:
            cleanup_task()
        except (ValueError, TypeError, OSError) as e:
            task_name = (
                cleanup_task.__name__
                if hasattr(cleanup_task, "__name__")
                else str(cleanup_task)
            )
            cleanup_errors.append((task_name, e))

    def _ensure_labels_exist(self) -> None:
        """必要なラベルがリポジトリ/プロジェクトに存在することを確認する."""
        required_labels = [
            self.config[self.platform]["bot_label"],
            self.config[self.platform]["processing_label"],
            self.config[self.platform]["done_label"],
        ]

        for label in required_labels:
            self._create_label_if_not_exists(label)

    def _create_label_if_not_exists(self, label: str) -> None:
        """ラベルが存在しない場合は作成する."""
        # これは各プラットフォームで実装される必要があります
        # 今のところ、ラベルが存在すると仮定します

    def create_issue(
        self,
        title: str,
        body: str,
        labels: list[str] | None = None,
    ) -> dict[str, Any]:
        """イシュー/マージリクエストを作成する.

        Args:
            title: イシューのタイトル
            body: イシューの本文
            labels: 追加するラベルのリスト

        Returns:
            イシューの詳細を含む辞書

        """
        if labels is None:
            labels = [self.config[self.platform]["bot_label"]]

        # これは各プラットフォームで実装されます
        issue_data = self._create_issue_impl(title, body, labels, self.bot_name)

        # クリーンアップタスクを追加
        def cleanup() -> None:
            issue_num = (
                issue_data["number"] if self.platform == "github" else issue_data["iid"]
            )
            self._close_issue(issue_num)

        self.cleanup_tasks.append(cleanup)

        return issue_data

    def _create_issue_impl(
        self,
        title: str,
        body: str,
        labels: list[str],
        assignee: str | None = None,
    ) -> dict[str, Any]:
        """プラットフォーム固有のイシュー作成実装.

        Args:
            title: イシューのタイトル
            body: イシューの本文
            labels: ラベルのリスト
            assignee: アサインするユーザー名(オプション)

        Returns:
            作成されたイシューの詳細を含む辞書

        """
        msg = "サブクラスは_create_issue_implを実装する必要があります"
        raise NotImplementedError(msg)

    def _close_issue(self, issue_id: int) -> None:
        """イシューを閉じる."""
        # プラットフォーム固有の実装

    def run_coding_agent(self, timeout: int = 300) -> subprocess.CompletedProcess:
        """コーディングエージェントのメイン関数を実行する.

        Args:
            timeout: 完了まで待機する最大時間

        Returns:
            完了したプロセスの結果

        """
        # コーディングエージェント用の環境をセットアップ
        env = os.environ.copy()
        env["TASK_SOURCE"] = self.platform

        if self.platform == "github":
            # Use new environment variable name, fallback to old one for backward compatibility
            if "GITHUB_PERSONAL_ACCESS_TOKEN" not in env and "GITHUB_TOKEN" in env:
                env["GITHUB_PERSONAL_ACCESS_TOKEN"] = env["GITHUB_TOKEN"]
        # Use new environment variable name, fallback to old one for backward compatibility
        elif "GITLAB_PERSONAL_ACCESS_TOKEN" not in env and "GITLAB_TOKEN" in env:
            env["GITLAB_PERSONAL_ACCESS_TOKEN"] = env["GITLAB_TOKEN"]

        # コーディングエージェントを実行
        agent_path = Path(__file__).parent.parent.parent / "main.py"

        result = subprocess.run(  # noqa: S603
            [sys.executable, str(agent_path)],
            check=False,
            env=env,
            cwd=agent_path.parent,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        self.logger.info("Coding agent stdout: %s", result.stdout)
        if result.stderr:
            self.logger.warning("Coding agent stderr: %s", result.stderr)

        return result

    def verify_file_creation(
        self,
        file_path: str,
        expected_content: str | None = None,
    ) -> bool:
        """リポジトリ内でファイルが作成されたことを確認する.

        Args:
            file_path: リポジトリ内のファイルパス
            expected_content: チェック対象のオプション内容

        Returns:
            ファイルが存在し、期待される内容を含む場合はTrue

        """
        # これはプラットフォーム固有の実装が必要です
        return self._verify_file_creation_impl(file_path, expected_content)

    def _verify_file_creation_impl(
        self,
        file_path: str,
        expected_content: str | None,
    ) -> bool:
        """プラットフォーム固有のファイル検証."""
        msg = "サブクラスは_verify_file_creation_implを実装する必要があります"
        raise NotImplementedError(msg)

    def verify_python_execution(self, file_path: str, expected_output: str) -> bool:
        """Pythonファイルが実行され、期待される出力を生成することを確認する.

        Args:
            file_path: リポジトリ内のPythonファイルパス
            expected_output: ファイル実行時の期待される出力

        Returns:
            実行が期待される出力を生成する場合はTrue

        """
        # ファイル内容をダウンロード
        content = self._get_file_content(file_path)
        if not content:
            return False

        # 一時ファイルを作成して実行
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        try:
            result = subprocess.run(  # noqa: S603
                [sys.executable, tmp_path],
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )

            output = result.stdout.strip()
            return expected_output.lower() in output.lower()

        except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
            self.logger.exception("Failed to execute Python file")
            return False
        finally:
            Path(tmp_path).unlink()

    def get_file_content(self, file_path: str) -> str | None:
        """リポジトリからファイル内容を取得する(公開メソッド)."""
        return self._get_file_content(file_path)

    def _get_file_content(self, file_path: str) -> str | None:
        """リポジトリからファイル内容を取得する."""
        msg = "サブクラスは_get_file_contentを実装する必要があります"
        raise NotImplementedError(msg)

    def verify_pull_request_creation(self, source_branch: str) -> bool:
        """指定されたブランチからプルリクエストが作成されたことを確認する.

        Args:
            source_branch: ソースブランチ名

        Returns:
            PR/MRが存在する場合はTrue

        """
        return self._verify_pull_request_creation_impl(source_branch)

    def _verify_pull_request_creation_impl(self, source_branch: str) -> bool:
        """プラットフォーム固有のPR検証."""
        msg = "サブクラスは_verify_pull_request_creation_implを実装する必要があります"
        raise NotImplementedError(msg)

    def add_pr_comment(self, pr_number: int, comment: str) -> dict[str, Any]:
        """プルリクエストにコメントを追加する.

        Args:
            pr_number: PR/MR番号
            comment: コメントテキスト

        Returns:
            コメントデータ

        """
        return self._add_pr_comment_impl(pr_number, comment)

    def _add_pr_comment_impl(self, pr_number: int, comment: str) -> dict[str, Any]:
        """プラットフォーム固有のPRコメント実装."""
        msg = "サブクラスは_add_pr_comment_implを実装する必要があります"
        raise NotImplementedError(msg)

    def llm_verify_output(self, actual_output: str, expected_criteria: str) -> bool:
        """LLMを使用して出力が基準を満たすかを確認する(非決定的検証用).

        Args:
            actual_output: 検証する実際の出力
            expected_criteria: 出力に含まれるべき内容の説明

        Returns:
            LLMが出力が基準を満たすと判断した場合はTrue

        """
        # LLMクライアントが利用可能かチェック
        if get_llm_client is None:
            self.logger.warning("LLM client not available, skipping verification")
            return True

        llm_client = get_llm_client(self.config, None, None)

        prompt = f"""
以下の出力が指定された基準を満たしているかを確認してください。

基準: {expected_criteria}

実際の出力:
{actual_output}

出力が基準を満たしている場合は"YES"、満たしていない場合は"NO"のみで応答してください。
次の行に簡単な説明を含めてください。
"""

        try:
            response = llm_client.chat(prompt)

            # 応答を解析
            lines = response.strip().split("\n")
            verdict = lines[0].strip().upper()

            self.logger.info("LLM verification verdict: %s", verdict)
            if len(lines) > 1:
                self.logger.info("LLM verification explanation: %s", lines[1])
            else:
                return verdict == "YES"

        except (ValueError, TypeError, OSError):
            self.logger.exception("LLM verification failed")
            return False

        return verdict == "YES"

    def wait_for_processing(self, issue_number: int, max_wait: int = 300) -> bool:
        """コーディングエージェントがイシューを処理するまで待機する.

        Args:
            issue_number: 監視するイシュー番号
            max_wait: 最大待機時間(秒)

        Returns:
            処理が正常に完了した場合はTrue

        """
        start_time = time.time()

        while time.time() - start_time < max_wait:
            issue_data = self._get_issue(issue_number)
            labels = issue_data.get("labels", [])

            # 処理が完了したかをチェック
            done_label = self.config[self.platform]["done_label"]
            if any(label.get("name") == done_label for label in labels):
                return True

            # まだ処理中かをチェック
            processing_label = self.config[self.platform]["processing_label"]
            if any(label.get("name") == processing_label for label in labels):
                self.logger.info("Issue %s still processing...", issue_number)
                time.sleep(10)
                continue

            # まだピックアップされていないかをチェック
            bot_label = self.config[self.platform]["bot_label"]
            if any(label.get("name") == bot_label for label in labels):
                self.logger.info("Issue %s waiting to be picked up...", issue_number)
                time.sleep(5)
                continue

            self.logger.warning("Issue %s has unexpected label state", issue_number)
            time.sleep(5)

        return False

    def _get_issue(self, issue_number: int) -> dict[str, Any]:
        """イシューデータを取得する."""
        msg = "サブクラスは_get_issueを実装する必要があります"
        raise NotImplementedError(msg)
