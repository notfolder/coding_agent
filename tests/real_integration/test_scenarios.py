"""Test scenarios for real integration testing.

This module implements the three test scenarios described in the issue:
1. Issue-based operation with hello_world.py creation
2. Issue-based pull request creation  
3. Pull request comment-based operation
"""
from __future__ import annotations

import logging
import subprocess
import time
import unittest
from typing import Optional

from .github_framework import GitHubRealIntegrationFramework
from .gitlab_framework import GitLabRealIntegrationFramework


class RealIntegrationTestScenarios(unittest.TestCase):
    """Real integration test scenarios using actual APIs."""

    def setUp(self) -> None:
        """Set up test environment."""
        # Determine which platform to test
        self.platform = self._get_test_platform()
        
        if self.platform == "github":
            self.framework = GitHubRealIntegrationFramework()
        elif self.platform == "gitlab":
            self.framework = GitLabRealIntegrationFramework()
        else:
            self.skipTest("No supported platform configured for testing")
            
        # Set up the test environment
        self.framework.setup_test_environment()
        
        # Store created issues for cleanup
        self.created_issues = []
        
    def tearDown(self) -> None:
        """Clean up test environment."""
        self.framework.teardown_test_environment()
        
    def _get_test_platform(self) -> Optional[str]:
        """Determine which platform to test based on environment variables."""
        import os
        
        if os.environ.get("GITHUB_TOKEN") and os.environ.get("GITHUB_TEST_REPO"):
            return "github"
        elif os.environ.get("GITLAB_TOKEN") and os.environ.get("GITLAB_TEST_PROJECT"):
            return "gitlab"
        else:
            return None
            
    def test_scenario_1_hello_world_creation(self) -> None:
        """Test Scenario 1: Issue-based operation to create hello_world.py.
        
        Creates an issue asking to create hello_world.py with main function
        that prints "hello world", assigns to coding agent, executes agent,
        and verifies the output.
        """
        logging.info("Starting Test Scenario 1: hello_world.py creation")
        
        # Step 1: Create issue
        issue_title = "Create hello_world.py file with main function"
        issue_body = """このリポジトリに"hello_world.py"ファイルを作成して、main関数を作り、"hello world"と出力するようにしてください。
このファイルを起動した際にmain関数を呼ばれる様にして。
pull requestは作成する必要ないので、mainブランチに直接コミットしてください。"""
        
        issue_data = self.framework.create_issue(issue_title, issue_body)
        issue_number = issue_data["number"] if self.platform == "github" else issue_data["iid"]
        self.created_issues.append(issue_number)
        
        logging.info("Created issue #%s: %s", issue_number, issue_title)
        
        # Step 2: Run coding agent
        logging.info("Running coding agent...")
        result = self.framework.run_coding_agent(timeout=600)  # 10 minutes timeout
        
        # Log the agent output for debugging
        logging.info("Agent return code: %s", result.returncode)
        if result.stdout:
            logging.info("Agent stdout: %s", result.stdout)
        if result.stderr:
            logging.warning("Agent stderr: %s", result.stderr)
            
        # Step 3: Wait for processing to complete
        logging.info("Waiting for issue processing to complete...")
        processing_completed = self.framework.wait_for_processing(issue_number, max_wait=600)
        
        if not processing_completed:
            self.fail("Issue processing did not complete within timeout")
            
        # Step 4: Verify file was created
        logging.info("Verifying hello_world.py file creation...")
        file_exists = self.framework.verify_file_creation("hello_world.py")
        self.assertTrue(file_exists, "hello_world.py file was not created")
        
        # Step 5: Verify file execution
        logging.info("Verifying hello_world.py execution...")
        execution_success = self.framework.verify_python_execution("hello_world.py", "hello world")
        
        if not execution_success:
            # Try LLM-based verification for more flexible checking
            file_content = self.framework._get_file_content("hello_world.py")
            if file_content:
                logging.info("File content: %s", file_content)
                llm_verified = self.framework.llm_verify_output(
                    file_content,
                    "Python file that contains a main function which prints 'hello world' and is executed when the file is run"
                )
                self.assertTrue(llm_verified, "LLM verification failed for hello_world.py content")
            else:
                self.fail("Could not retrieve hello_world.py content for verification")
        
        logging.info("Test Scenario 1 completed successfully")
        
    def test_scenario_2_pull_request_creation(self) -> None:
        """Test Scenario 2: Issue-based pull request creation.
        
        Creates an issue asking to modify hello_world.py to add scikit-learn
        iris dataset classification, create branch, and create pull request.
        """
        logging.info("Starting Test Scenario 2: Pull request creation")
        
        # Prerequisite: Ensure hello_world.py exists (run scenario 1 first if needed)
        if not self.framework.verify_file_creation("hello_world.py"):
            logging.info("hello_world.py doesn't exist, running scenario 1 first...")
            self.test_scenario_1_hello_world_creation()
            
        # Step 1: Create issue for modification
        issue_title = "Modify hello_world.py to add scikit-learn iris classification"
        issue_body = """既存のhello_world.pyの内容を変更したいです。下記の手順に従ってソースコードの変更作業を行ってください。
1. `hello_world.py`ファイルを読み込んで現在のコードを理解して
2. 下記の変更をするためにブランチを作成して
3. `hello_world.py`ファイルを変更して、scikit-learnのirisデータセットを分類する関数を作ってmain関数から呼び出す様にして
4. プルリクエストを作成して"""
        
        issue_data = self.framework.create_issue(issue_title, issue_body)
        issue_number = issue_data["number"] if self.platform == "github" else issue_data["iid"]
        self.created_issues.append(issue_number)
        
        logging.info("Created issue #%s: %s", issue_number, issue_title)
        
        # Step 2: Run coding agent
        logging.info("Running coding agent...")
        result = self.framework.run_coding_agent(timeout=600)
        
        # Log the agent output
        logging.info("Agent return code: %s", result.returncode)
        if result.stdout:
            logging.info("Agent stdout: %s", result.stdout)
        if result.stderr:
            logging.warning("Agent stderr: %s", result.stderr)
            
        # Step 3: Wait for processing to complete
        logging.info("Waiting for issue processing to complete...")
        processing_completed = self.framework.wait_for_processing(issue_number, max_wait=600)
        
        if not processing_completed:
            self.fail("Issue processing did not complete within timeout")
            
        # Step 4: Verify branch creation and pull request
        logging.info("Verifying pull request creation...")
        
        # Check for common branch naming patterns
        possible_branches = [
            "feature/iris-classification",
            "iris-classification", 
            "scikit-learn-iris",
            "feature/scikit-learn",
            "update-hello-world",
        ]
        
        pr_created = False
        for branch_name in possible_branches:
            if self.framework.verify_pull_request_creation(branch_name):
                pr_created = True
                logging.info("Found pull request from branch: %s", branch_name)
                break
                
        if not pr_created:
            # Check for any recent pull requests
            if hasattr(self.framework, 'get_latest_pull_request'):
                latest_pr = self.framework.get_latest_pull_request()
                if latest_pr:
                    pr_created = True
                    logging.info("Found latest pull request: #%s", latest_pr["number"])
                    
        self.assertTrue(pr_created, "Pull request was not created")
        
        logging.info("Test Scenario 2 completed successfully")
        
    def test_scenario_3_pr_comment_operation(self) -> None:
        """Test Scenario 3: Pull request comment-based operation.
        
        Adds comment to existing PR asking to modify file for multiple
        classification model evaluation with accuracy and confusion matrix.
        """
        logging.info("Starting Test Scenario 3: PR comment operation")
        
        # Prerequisite: Ensure there's an open PR (run scenario 2 first if needed)
        latest_pr = None
        if hasattr(self.framework, 'get_latest_pull_request'):
            latest_pr = self.framework.get_latest_pull_request()
        elif hasattr(self.framework, 'get_latest_merge_request'):
            latest_pr = self.framework.get_latest_merge_request()
            
        if not latest_pr:
            logging.info("No open PR/MR found, running scenario 2 first...")
            self.test_scenario_2_pull_request_creation()
            
            # Get the latest PR again
            if hasattr(self.framework, 'get_latest_pull_request'):
                latest_pr = self.framework.get_latest_pull_request()
            elif hasattr(self.framework, 'get_latest_merge_request'):
                latest_pr = self.framework.get_latest_merge_request()
                
        if not latest_pr:
            self.fail("Could not find or create a pull request for testing")
            
        pr_number = latest_pr["number"] if self.platform == "github" else latest_pr["iid"]
        
        # Step 1: Add comment to PR
        comment_text = """1. hello_world.pyファイルを読み込んで現在のコードを理解して
2. hello_world.pyファイルを変更して、scikit-learnの複数の分類モデルでそれぞれ性能を正答率と混同行列評価できる様に修正して
3. レビューや議論は必要ないので、このブランチにコミットして"""
        
        # Add coding agent label to the comment (implementation-specific)
        labels = [self.framework.config[self.platform]["bot_label"]]
        
        comment_data = self.framework.add_pr_comment(pr_number, comment_text)
        logging.info("Added comment to PR #%s", pr_number)
        
        # Step 2: Run coding agent
        logging.info("Running coding agent...")
        result = self.framework.run_coding_agent(timeout=600)
        
        # Log the agent output
        logging.info("Agent return code: %s", result.returncode)
        if result.stdout:
            logging.info("Agent stdout: %s", result.stdout)
        if result.stderr:
            logging.warning("Agent stderr: %s", result.stderr)
            
        # Step 3: Wait for processing (this is tricky for comments, so we'll wait a bit)
        logging.info("Waiting for comment processing...")
        time.sleep(30)  # Give some time for processing
        
        # Step 4: Verify the file was updated with multiple models and evaluation
        logging.info("Verifying hello_world.py updates...")
        
        # Get the updated file content
        file_content = self.framework._get_file_content("hello_world.py")
        self.assertIsNotNone(file_content, "Could not retrieve updated hello_world.py content")
        
        # Use LLM to verify the content meets requirements
        llm_verified = self.framework.llm_verify_output(
            file_content,
            "Python code that uses multiple scikit-learn classification models to evaluate performance with accuracy scores and confusion matrices"
        )
        self.assertTrue(llm_verified, "LLM verification failed for updated hello_world.py content")
        
        # Step 5: Try to execute the file and verify output contains accuracy and confusion matrix
        try:
            execution_success = self.framework.verify_python_execution("hello_world.py", "accuracy")
            if execution_success:
                logging.info("File execution successful with accuracy output")
            else:
                # Alternative verification: check for imports and key terms
                imports_verified = self.framework.llm_verify_output(
                    file_content,
                    "Contains imports for scikit-learn models and evaluation metrics, and includes code for accuracy and confusion matrix evaluation"
                )
                self.assertTrue(imports_verified, "File does not appear to contain required ML evaluation code")
                
        except Exception as e:
            logging.warning("Could not execute file for verification: %s", e)
            # Fall back to content analysis
            content_verified = self.framework.llm_verify_output(
                file_content,
                "Contains code for multiple classification models, accuracy evaluation, and confusion matrix computation"
            )
            self.assertTrue(content_verified, "File content does not meet requirements based on LLM analysis")
            
        logging.info("Test Scenario 3 completed successfully")


if __name__ == "__main__":
    # Configure logging for test execution
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    unittest.main()