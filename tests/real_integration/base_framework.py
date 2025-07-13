"""Base framework for real integration tests.

This module provides the base infrastructure for running integration tests
that use actual GitHub/GitLab and LLM APIs rather than mocks.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Optional

import yaml


class RealIntegrationTestFramework:
    """Framework for running real integration tests."""

    def __init__(self, platform: str = "github") -> None:
        """Initialize the test framework.
        
        Args:
            platform: Either "github" or "gitlab"
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
        
    def _check_prerequisites(self) -> None:
        """Check that required environment variables are set."""
        if self.platform == "github":
            if not os.environ.get("GITHUB_TOKEN"):
                raise ValueError("GITHUB_TOKEN environment variable is required for GitHub tests")
            if not os.environ.get("GITHUB_TEST_REPO"):
                raise ValueError("GITHUB_TEST_REPO environment variable is required (format: owner/repo)")
        elif self.platform == "gitlab":
            if not os.environ.get("GITLAB_TOKEN"):
                raise ValueError("GITLAB_TOKEN environment variable is required for GitLab tests")
            if not os.environ.get("GITLAB_TEST_PROJECT"):
                raise ValueError("GITLAB_TEST_PROJECT environment variable is required")
                
        # Check for LLM configuration
        llm_provider = os.environ.get("LLM_PROVIDER", "openai")
        if llm_provider == "openai" and not os.environ.get("OPENAI_API_KEY"):
            raise ValueError("OPENAI_API_KEY environment variable is required when using OpenAI")
            
    def _load_config(self) -> dict[str, Any]:
        """Load test configuration."""
        config_path = Path(__file__).parent.parent / f"real_test_config_{self.platform}.yaml"
        
        if not config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")
            
        with config_path.open() as f:
            config = yaml.safe_load(f)
            
        # Override with environment variables
        if self.platform == "github":
            repo_parts = os.environ.get("GITHUB_TEST_REPO", "").split("/")
            if len(repo_parts) == 2:
                config["github"]["owner"] = repo_parts[0]
                config["github"]["repo"] = repo_parts[1]
                self.test_repo = f"{repo_parts[0]}/{repo_parts[1]}"
        elif self.platform == "gitlab":
            project = os.environ.get("GITLAB_TEST_PROJECT")
            if project:
                config["gitlab"]["project_id"] = project
                self.test_project_id = project
                
        return config
        
    def setup_test_environment(self) -> None:
        """Set up the test environment."""
        self.logger.info("Setting up test environment for %s", self.platform)
        
        # Ensure test labels exist
        self._ensure_labels_exist()
        
    def teardown_test_environment(self) -> None:
        """Clean up test environment."""
        self.logger.info("Cleaning up test environment")
        
        # Execute cleanup tasks in reverse order
        for cleanup_task in reversed(self.cleanup_tasks):
            try:
                cleanup_task()
            except Exception as e:
                self.logger.warning("Cleanup task failed: %s", e)
                
    def _ensure_labels_exist(self) -> None:
        """Ensure required labels exist in the repository/project."""
        required_labels = [
            self.config[self.platform]["bot_label"],
            self.config[self.platform]["processing_label"],
            self.config[self.platform]["done_label"],
        ]
        
        for label in required_labels:
            self._create_label_if_not_exists(label)
            
    def _create_label_if_not_exists(self, label: str) -> None:
        """Create a label if it doesn't exist."""
        # This would need to be implemented for each platform
        # For now, we'll assume labels exist
        pass
        
    def create_issue(self, title: str, body: str, labels: Optional[list[str]] = None) -> dict[str, Any]:
        """Create an issue/merge request.
        
        Args:
            title: Issue title
            body: Issue body
            labels: List of labels to add
            
        Returns:
            Dictionary containing issue details
        """
        if labels is None:
            labels = [self.config[self.platform]["bot_label"]]
            
        # This will be implemented per platform
        issue_data = self._create_issue_impl(title, body, labels)
        
        # Add cleanup task
        def cleanup():
            self._close_issue(issue_data["number"] if self.platform == "github" else issue_data["iid"])
            
        self.cleanup_tasks.append(cleanup)
        
        return issue_data
        
    def _create_issue_impl(self, title: str, body: str, labels: list[str]) -> dict[str, Any]:
        """Platform-specific issue creation implementation."""
        raise NotImplementedError("Subclasses must implement _create_issue_impl")
        
    def _close_issue(self, issue_id: int) -> None:
        """Close an issue."""
        # Platform-specific implementation
        pass
        
    def run_coding_agent(self, timeout: int = 300) -> subprocess.CompletedProcess:
        """Run the coding agent main function.
        
        Args:
            timeout: Maximum time to wait for completion
            
        Returns:
            Completed process result
        """
        # Set up environment for the coding agent
        env = os.environ.copy()
        env["TASK_SOURCE"] = self.platform
        
        if self.platform == "github":
            env["GITHUB_PERSONAL_ACCESS_TOKEN"] = env["GITHUB_TOKEN"]
        else:
            env["GITLAB_PERSONAL_ACCESS_TOKEN"] = env["GITLAB_TOKEN"]
            
        # Use the test configuration
        config_file = f"real_test_config_{self.platform}.yaml"
        
        # Run the coding agent
        agent_path = Path(__file__).parent.parent.parent / "main.py"
        
        result = subprocess.run(
            ["python", str(agent_path)],
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
        
    def verify_file_creation(self, file_path: str, expected_content: Optional[str] = None) -> bool:
        """Verify that a file was created in the repository.
        
        Args:
            file_path: Path to the file in the repository
            expected_content: Optional content to check for
            
        Returns:
            True if file exists and contains expected content
        """
        # This would need platform-specific implementation
        return self._verify_file_creation_impl(file_path, expected_content)
        
    def _verify_file_creation_impl(self, file_path: str, expected_content: Optional[str]) -> bool:
        """Platform-specific file verification."""
        raise NotImplementedError("Subclasses must implement _verify_file_creation_impl")
        
    def verify_python_execution(self, file_path: str, expected_output: str) -> bool:
        """Verify that a Python file executes and produces expected output.
        
        Args:
            file_path: Path to the Python file in the repository
            expected_output: Expected output when running the file
            
        Returns:
            True if execution produces expected output
        """
        # Download the file content
        content = self._get_file_content(file_path)
        if not content:
            return False
            
        # Create a temporary file and execute it
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name
            
        try:
            result = subprocess.run(
                ["python", tmp_path],
                capture_output=True,
                text=True,
                timeout=30,
            )
            
            output = result.stdout.strip()
            return expected_output.lower() in output.lower()
            
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as e:
            self.logger.error("Failed to execute Python file: %s", e)
            return False
        finally:
            os.unlink(tmp_path)
            
    def _get_file_content(self, file_path: str) -> Optional[str]:
        """Get file content from repository."""
        raise NotImplementedError("Subclasses must implement _get_file_content")
        
    def verify_pull_request_creation(self, source_branch: str) -> bool:
        """Verify that a pull request was created from the specified branch.
        
        Args:
            source_branch: Source branch name
            
        Returns:
            True if PR/MR exists
        """
        return self._verify_pull_request_creation_impl(source_branch)
        
    def _verify_pull_request_creation_impl(self, source_branch: str) -> bool:
        """Platform-specific PR verification."""
        raise NotImplementedError("Subclasses must implement _verify_pull_request_creation_impl")
        
    def add_pr_comment(self, pr_number: int, comment: str) -> dict[str, Any]:
        """Add a comment to a pull request.
        
        Args:
            pr_number: PR/MR number
            comment: Comment text
            
        Returns:
            Comment data
        """
        return self._add_pr_comment_impl(pr_number, comment)
        
    def _add_pr_comment_impl(self, pr_number: int, comment: str) -> dict[str, Any]:
        """Platform-specific PR comment implementation."""
        raise NotImplementedError("Subclasses must implement _add_pr_comment_impl")
        
    def llm_verify_output(self, actual_output: str, expected_criteria: str) -> bool:
        """Use LLM to verify if output meets criteria (for non-deterministic verification).
        
        Args:
            actual_output: Actual output to verify
            expected_criteria: Description of what the output should contain
            
        Returns:
            True if LLM determines output meets criteria
        """
        # Import LLM client
        from clients.lm_client import get_llm_client
        
        llm_client = get_llm_client(self.config, None, None)
        
        prompt = f"""
Please verify if the following output meets the specified criteria.

Criteria: {expected_criteria}

Actual Output:
{actual_output}

Respond with only "YES" if the output meets the criteria, or "NO" if it doesn't.
Include a brief explanation on the next line.
"""
        
        try:
            response = llm_client.chat(prompt)
            
            # Parse response
            lines = response.strip().split('\n')
            verdict = lines[0].strip().upper()
            
            self.logger.info("LLM verification verdict: %s", verdict)
            if len(lines) > 1:
                self.logger.info("LLM verification explanation: %s", lines[1])
                
            return verdict == "YES"
            
        except Exception as e:
            self.logger.error("LLM verification failed: %s", e)
            return False
            
    def wait_for_processing(self, issue_number: int, max_wait: int = 300) -> bool:
        """Wait for the coding agent to process an issue.
        
        Args:
            issue_number: Issue number to monitor
            max_wait: Maximum time to wait in seconds
            
        Returns:
            True if processing completed successfully
        """
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            issue_data = self._get_issue(issue_number)
            labels = issue_data.get("labels", [])
            
            # Check if processing is complete
            done_label = self.config[self.platform]["done_label"]
            if any(label.get("name") == done_label for label in labels):
                return True
                
            # Check if still processing
            processing_label = self.config[self.platform]["processing_label"]
            if any(label.get("name") == processing_label for label in labels):
                self.logger.info("Issue %s still processing...", issue_number)
                time.sleep(10)
                continue
                
            # Check if not yet picked up
            bot_label = self.config[self.platform]["bot_label"]
            if any(label.get("name") == bot_label for label in labels):
                self.logger.info("Issue %s waiting to be picked up...", issue_number)
                time.sleep(5)
                continue
                
            self.logger.warning("Issue %s has unexpected label state", issue_number)
            time.sleep(5)
            
        return False
        
    def _get_issue(self, issue_number: int) -> dict[str, Any]:
        """Get issue data."""
        raise NotImplementedError("Subclasses must implement _get_issue")