"""リアル統合テスト用のテストシナリオ.

このモジュールは、イシューで説明された3つのテストシナリオを実装します:
1. hello_world.py作成によるイシューベースの操作
2. イシューベースのプルリクエスト作成
3. プルリクエストコメントベースの操作
"""
from __future__ import annotations

import logging
import os
import subprocess
import time
import unittest
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tests.real_integration.base_framework import RealIntegrationTestFramework

from tests.real_integration.github_framework import GitHubRealIntegrationFramework
from tests.real_integration.gitlab_framework import GitLabRealIntegrationFramework


class RealIntegrationTestScenarios(unittest.TestCase):
    """実際のAPIを使用するリアル統合テストシナリオ."""

    @classmethod
    def setUpClass(cls) -> None:
        # テストするプラットフォームを決定
        cls.platforms = cls._get_test_platforms()

        if not cls.platforms:
            msg = "No supported platform configured for testing"
            raise unittest.SkipTest(msg)

        # 各プラットフォーム用のフレームワークを初期化
        cls.frameworks = {}
        for platform in cls.platforms:
            if platform == "github":
                cls.frameworks[platform] = GitHubRealIntegrationFramework()
            elif platform == "gitlab":
                cls.frameworks[platform] = GitLabRealIntegrationFramework()

        # 各プラットフォームでテスト環境をセットアップ
        for framework in cls.frameworks.values():
            framework.setup_test_environment()

    def setUp(self) -> None:
        """テスト環境をセットアップする."""
        # ロガーをセットアップ
        self.logger = logging.getLogger(__name__)

        # Store created issues for cleanup (per platform)
        self.created_issues = {}
        for platform in self.platforms:
            self.created_issues[platform] = []

    @classmethod
    def tearDownClass(cls) -> None:
        """Clean up test environment."""
        for framework in cls.frameworks.values():
            framework.teardown_test_environment()

    @classmethod
    def _get_test_platforms(cls) -> list[str]:
        """Determine which platforms to test based on environment variables."""
        platforms = []


        github_token = (
            os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN")
            or os.environ.get("GITHUB_TOKEN")
        )
        github_repo = os.environ.get("GITHUB_TEST_REPO")

        gitlab_token = (
            os.environ.get("GITLAB_PERSONAL_ACCESS_TOKEN")
            or os.environ.get("GITLAB_TOKEN")
        )
        gitlab_project = os.environ.get("GITLAB_TEST_PROJECT")

        if github_token and github_repo:
            platforms.append("github")
        if gitlab_token and gitlab_project:
            platforms.append("gitlab")

        return platforms

    def test_scenario_1_hello_world_creation(self) -> None:
        """Test Scenario 1: Issue-based operation to create hello_world.py.

        Creates an issue asking to create hello_world.py with main function
        that prints "hello world", assigns to coding agent, executes agent,
        and verifies the output.
        """
        for platform in self.platforms:
            with self.subTest(platform=platform):
                self._test_scenario_1_for_platform(platform)

    def _test_scenario_1_for_platform(self, platform: str) -> None:
        """Test scenario 1 for a specific platform."""
        framework = self.frameworks[platform]
        self.logger.info(
            "Starting Test Scenario 1: hello_world.py creation for %s", platform,
        )

        # Step 1: Create issue
        issue_title = "Create hello_world.py file with main function"
        issue_body = """このリポジトリに"hello_world.py"ファイルを作成して、main関数を作り、
"hello world"と出力するようにしてください。
このファイルを起動した際にmain関数を呼ばれる様にして。
pull requestは作成する必要ないので、mainブランチに直接コミットしてください。"""

        issue_data = framework.create_issue(issue_title, issue_body)
        issue_number = issue_data["number"] if platform == "github" else issue_data["iid"]
        self.created_issues[platform].append(issue_number)

        self.logger.info("Created issue #%s: %s", issue_number, issue_title)

        # Step 2: Run coding agent
        self.logger.info("Running coding agent...")
        result = framework.run_coding_agent(timeout=3600)  # 1 hour timeout

        # Log the agent output for debugging
        self.logger.info("Agent return code: %s", result.returncode)
        if result.stdout:
            self.logger.info("Agent stdout: %s", result.stdout)
        if result.stderr:
            self.logger.warning("Agent stderr: %s", result.stderr)

        # Step 3: Wait for processing to complete
        self.logger.info("Waiting for issue processing to complete...")
        processing_completed = framework.wait_for_processing(issue_number, max_wait=3600)

        if not processing_completed:
            self.fail("Issue processing did not complete within timeout")

        # Step 4: Verify file was created
        self.logger.info("Verifying hello_world.py file creation...")
        file_exists = framework.verify_file_creation("hello_world.py")
        assert file_exists, "hello_world.py file was not created"

        # Step 5: Verify file execution
        self.logger.info("Verifying hello_world.py execution...")
        execution_success = framework.verify_python_execution("hello_world.py", "hello world")

        if not execution_success:
            # Try LLM-based verification for more flexible checking
            file_content = framework.get_file_content("hello_world.py")
            if file_content:
                self.logger.info("File content: %s", file_content)
                llm_verified = framework.llm_verify_output(
                    file_content,
                    "Python file that contains a main function which prints 'hello world'"
                    " and is executed when the file is run",
                )
                assert llm_verified, "LLM verification failed for hello_world.py content"
            else:
                self.fail("Could not retrieve hello_world.py content for verification")

        self.logger.info("Test Scenario 1 completed successfully for %s", platform)

    def test_scenario_2_pull_request_creation(self) -> None:
        """Test Scenario 2: Issue-based pull request creation.

        Creates an issue asking to modify hello_world.py to add scikit-learn
        iris dataset classification, create branch, and create pull request.
        """
        for platform in self.platforms:
            with self.subTest(platform=platform):
                self._test_scenario_2_for_platform(platform)

    def _test_scenario_2_for_platform(self, platform: str) -> None:  # noqa: C901
        """Test scenario 2 for a specific platform."""
        framework = self.frameworks[platform]
        self.logger.info(
            "Starting Test Scenario 2: Pull request creation for %s", platform,
        )

        # Prerequisite: Ensure hello_world.py exists (run scenario 1 first if needed)
        if not framework.verify_file_creation("hello_world.py"):
            self.logger.info("hello_world.py doesn't exist, running scenario 1 first...")
            self._test_scenario_1_for_platform(platform)

        # Step 1: Create issue for modification
        issue_title = "Modify hello_world.py to add scikit-learn iris classification"
        pr_word = "プルリクエスト" if platform == "github" else "マージリクエスト"
        issue_body = f"""既存のhello_world.pyの内容を変更したいです。下記の手順に従って
ソースコードの変更作業を行ってください。
1. `hello_world.py`ファイルを読み込んで現在のコードを理解して
2. 下記の変更をするためにブランチを作成して
3. `hello_world.py`ファイルを変更して、scikit-learnのirisデータセットを分類、評価する
関数を作ってmain関数から呼び出す様にして
4. {pr_word}を作成して"""

        issue_data = framework.create_issue(issue_title, issue_body)
        issue_number = issue_data["number"] if platform == "github" else issue_data["iid"]
        self.created_issues[platform].append(issue_number)

        self.logger.info("Created issue #%s: %s", issue_number, issue_title)

        # Step 2: Run coding agent
        self.logger.info("Running coding agent...")
        result = framework.run_coding_agent(timeout=3600)

        # Log the agent output
        self.logger.info("Agent return code: %s", result.returncode)
        if result.stdout:
            self.logger.info("Agent stdout: %s", result.stdout)
        if result.stderr:
            self.logger.warning("Agent stderr: %s", result.stderr)

        # Step 3: Wait for processing to complete
        self.logger.info("Waiting for issue processing to complete...")
        processing_completed = framework.wait_for_processing(issue_number, max_wait=3600)

        if not processing_completed:
            self.fail("Issue processing did not complete within timeout")

        # Step 4: Verify branch creation and pull request
        self.logger.info("Verifying pull request creation...")

        # Check for common branch naming patterns
        possible_branches = [
            "feature/iris-classification",
            "iris-classification",
            "scikit-learn-iris",
            "feature/scikit-learn",
            "update-hello-world",
        ]

        pr_created = False
        pr_number = None
        for branch_name in possible_branches:
            if framework.verify_pull_request_creation(branch_name):
                pr_created = True
                self.logger.info("Found pull request from branch: %s", branch_name)
                # Get the PR number to add label and assignment
                if hasattr(framework, "get_latest_pull_request"):
                    latest_pr = framework.get_latest_pull_request(branch_name)
                    if latest_pr:
                        pr_number = (
                            latest_pr["number"] if platform == "github" else latest_pr["iid"]
                        )
                break

        if not pr_created and hasattr(framework, "get_latest_pull_request"):
            latest_pr = framework.get_latest_pull_request()
            if latest_pr:
                pr_created = True
                pr_number = latest_pr["number"] if platform == "github" else latest_pr["iid"]
                self.logger.info("Found latest pull request: #%s", pr_number)

        assert pr_created, "Pull request was not created"

        # GitHubプルリクエストの場合、コーディングエージェント用のラベルを追加し、アサインする
        if pr_number and platform == "github":
            self._enhance_github_pull_request(framework, pr_number)
        elif pr_number and platform == "gitlab":
            self._enhance_gitlab_merge_request(framework, pr_number)

        self.logger.info("Test Scenario 2 completed successfully for %s", platform)

    def test_scenario_3_pr_comment_operation(self) -> None:
        """Test Scenario 3: Pull request comment-based operation.

        Adds comment to existing PR asking to modify file for multiple
        classification model evaluation with accuracy and confusion matrix.
        """
        for platform in self.platforms:
            with self.subTest(platform=platform):
                self._test_scenario_3_for_platform(platform)

    def _test_scenario_3_for_platform(self, platform: str) -> None:
        """Test scenario 3 for a specific platform."""
        framework = self.frameworks[platform]
        self.logger.info(
            "Starting Test Scenario 3: PR comment operation for %s", platform,
        )

        # Get or create a PR for testing
        pr_number = self._get_or_create_pr_for_scenario_3(platform)

        # Add comment and run agent
        self._add_comment_and_run_agent(platform, pr_number)

        # Verify the results
        self._verify_scenario_3_results(framework)

        self.logger.info("Test Scenario 3 completed successfully for %s", platform)

    def _get_or_create_pr_for_scenario_3(self, platform: str) -> int:
        """Get existing PR or create one for scenario 3."""
        framework = self.frameworks[platform]

        # Prerequisite: Ensure there's an open PR (run scenario 2 first if needed)
        latest_pr = None
        if hasattr(framework, "get_latest_pull_request"):
            latest_pr = framework.get_latest_pull_request()
        elif hasattr(framework, "get_latest_merge_request"):
            latest_pr = framework.get_latest_merge_request()

        if not latest_pr:
            self.logger.info("No open PR/MR found, running scenario 2 first...")
            self._test_scenario_2_for_platform(platform)

            # Get the latest PR again
            if hasattr(framework, "get_latest_pull_request"):
                latest_pr = framework.get_latest_pull_request()
            elif hasattr(framework, "get_latest_merge_request"):
                latest_pr = framework.get_latest_merge_request()

        if not latest_pr:
            self.fail("Could not find or create a pull request for testing")

        return latest_pr["number"] if platform == "github" else latest_pr["iid"]

    def _add_comment_and_run_agent(self, platform: str, pr_number: int) -> None:
        """Add comment to PR and run the coding agent."""
        framework = self.frameworks[platform]

        # Step 1: Add comment to PR
        comment_text = """1. hello_world.pyファイルを読み込んで現在のコードを理解して
2. hello_world.pyファイルを変更して、scikit-learnの複数の分類モデルで
それぞれ性能を正答率と混同行列評価できる様に修正して
3. レビューや議論は必要ないので、このブランチにコミットして"""

        # Add coding agent label to the comment (implementation-specific)
        framework.add_pr_comment(pr_number, comment_text)
        self.logger.info("Added comment to PR #%s", pr_number)

        # PRにコーディングエージェント用のラベルとアサインメントを追加
        if platform == "github":
            self._enhance_github_pull_request(framework, pr_number)
        elif platform == "gitlab":
            self._enhance_gitlab_merge_request(framework, pr_number)

        # Step 2: Run coding agent
        self.logger.info("Running coding agent...")
        result = framework.run_coding_agent(timeout=3600)

        # Log the agent output
        self.logger.info("Agent return code: %s", result.returncode)
        if result.stdout:
            self.logger.info("Agent stdout: %s", result.stdout)
        if result.stderr:
            self.logger.warning("Agent stderr: %s", result.stderr)

        # Step 3: Wait for processing (this is tricky for comments, so we'll wait a bit)
        self.logger.info("Waiting for comment processing...")
        time.sleep(30)  # Give some time for processing

    def _verify_scenario_3_results(self, framework: RealIntegrationTestFramework) -> None:
        """Verify the results of scenario 3."""
        # Step 4: Verify the file was updated with multiple models and evaluation
        self.logger.info("Verifying hello_world.py updates...")

        # Get the updated file content
        file_content = framework.get_file_content("hello_world.py")
        assert file_content is not None, "Could not retrieve updated hello_world.py content"

        # Use LLM to verify the content meets requirements
        llm_verified = framework.llm_verify_output(
            file_content,
            "Python code that uses multiple scikit-learn classification models "
            "to evaluate performance with accuracy scores and confusion matrices",
        )
        assert llm_verified, "LLM verification failed for updated hello_world.py content"

        # Step 5: Try to execute the file and verify output contains accuracy and confusion matrix
        self._verify_execution_or_content(framework, file_content)

    def _verify_execution_or_content(self, framework: RealIntegrationTestFramework, file_content: str) -> None:
        """Verify file execution or analyze content as fallback."""
        try:
            execution_success = framework.verify_python_execution(
                "hello_world.py", "accuracy",
            )
            if execution_success:
                self.logger.info("File execution successful with accuracy output")
            else:
                # Alternative verification: check for imports and key terms
                imports_verified = framework.llm_verify_output(
                    file_content,
                    "Contains imports for scikit-learn models and evaluation metrics, "
                    "and includes code for accuracy and confusion matrix evaluation",
                )
                assert imports_verified, (
                    "File does not appear to contain required ML evaluation code"
                )

        except (OSError, subprocess.SubprocessError, FileNotFoundError) as e:
            self.logger.warning("Could not execute file for verification: %s", e)
            # Fall back to content analysis
            content_verified = framework.llm_verify_output(
                file_content,
                "Contains code for multiple classification models, accuracy evaluation, "
                "and confusion matrix computation",
            )
            assert content_verified, "File content does not meet requirements based on LLM analysis"

    def _enhance_github_pull_request(self, framework: RealIntegrationTestFramework, pr_number: int) -> None:
        """GitHubプルリクエストにコーディングエージェント用のラベルとアサインメントを追加する.

        Args:
            framework: フレームワークインスタンス
            pr_number: プルリクエスト番号

        """
        self.logger.info(
            "Enhancing GitHub pull request #%s with coding agent label and assignment",
            pr_number,
        )

        # コーディングエージェント用のラベルを追加
        bot_label = framework.config["github"]["bot_label"]
        if hasattr(framework, "add_label_to_pull_request"):
            success = framework.add_label_to_pull_request(pr_number, bot_label)
            if success:
                self.logger.info("Added coding agent label to PR #%s", pr_number)
            else:
                self.logger.warning("Failed to add coding agent label to PR #%s", pr_number)

        # コーディングエージェントをアサインする
        bot_name = framework.get_bot_name()
        if bot_name and hasattr(framework, "assign_pull_request"):
            success = framework.assign_pull_request(pr_number, bot_name)
            if success:
                self.logger.info("Assigned coding agent to PR #%s", pr_number)
            else:
                self.logger.warning("Failed to assign coding agent to PR #%s", pr_number)

    def _enhance_gitlab_merge_request(self, framework: RealIntegrationTestFramework, mr_iid: int) -> None:
        """GitLabマージリクエストにコーディングエージェント用のラベルとアサインメントを追加する.

        Args:
            framework: フレームワークインスタンス
            mr_iid: マージリクエストのIID

        """
        self.logger.info(
            "Enhancing GitLab merge request #%s with coding agent label and assignment",
            mr_iid,
        )

        # コーディングエージェント用のラベルを追加
        bot_label = framework.config["gitlab"]["bot_label"]
        if hasattr(framework, "add_label_to_merge_request"):
            success = framework.add_label_to_merge_request(mr_iid, bot_label)
            if success:
                self.logger.info("Added coding agent label to MR #%s", mr_iid)
            else:
                self.logger.warning("Failed to add coding agent label to MR #%s", mr_iid)

        # コーディングエージェントをアサインする
        bot_name = framework.get_bot_name()
        if bot_name and hasattr(framework, "assign_merge_request"):
            success = framework.assign_merge_request(mr_iid, bot_name)
            if success:
                self.logger.info("Assigned coding agent to MR #%s", mr_iid)
            else:
                self.logger.warning("Failed to assign coding agent to MR #%s", mr_iid)


if __name__ == "__main__":
    # Configure logging for test execution
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    unittest.main()
