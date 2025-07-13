"""GitHub-specific implementation of real integration test framework."""
from __future__ import annotations

import os
import requests
from typing import Any, Optional

from .base_framework import RealIntegrationTestFramework


class GitHubRealIntegrationFramework(RealIntegrationTestFramework):
    """GitHub-specific real integration test framework."""

    def __init__(self) -> None:
        """Initialize GitHub test framework."""
        super().__init__("github")
        self.api_base = "https://api.github.com"
        self.headers = {
            "Authorization": f"token {os.environ['GITHUB_TOKEN']}",
            "Accept": "application/vnd.github.v3+json",
        }
        
    def _create_issue_impl(self, title: str, body: str, labels: list[str]) -> dict[str, Any]:
        """Create a GitHub issue."""
        owner, repo = self.test_repo.split("/")
        
        url = f"{self.api_base}/repos/{owner}/{repo}/issues"
        data = {
            "title": title,
            "body": body,
            "labels": labels,
        }
        
        response = requests.post(url, json=data, headers=self.headers)
        response.raise_for_status()
        
        issue_data = response.json()
        self.logger.info("Created GitHub issue #%s: %s", issue_data["number"], title)
        
        return issue_data
        
    def _close_issue(self, issue_number: int) -> None:
        """Close a GitHub issue."""
        owner, repo = self.test_repo.split("/")
        
        url = f"{self.api_base}/repos/{owner}/{repo}/issues/{issue_number}"
        data = {"state": "closed"}
        
        response = requests.patch(url, json=data, headers=self.headers)
        response.raise_for_status()
        
        self.logger.info("Closed GitHub issue #%s", issue_number)
        
    def _get_issue(self, issue_number: int) -> dict[str, Any]:
        """Get GitHub issue data."""
        owner, repo = self.test_repo.split("/")
        
        url = f"{self.api_base}/repos/{owner}/{repo}/issues/{issue_number}"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        
        return response.json()
        
    def _verify_file_creation_impl(self, file_path: str, expected_content: Optional[str]) -> bool:
        """Verify file creation in GitHub repository."""
        content = self._get_file_content(file_path)
        if not content:
            return False
            
        if expected_content:
            return expected_content in content
            
        return True
        
    def _get_file_content(self, file_path: str) -> Optional[str]:
        """Get file content from GitHub repository."""
        owner, repo = self.test_repo.split("/")
        
        url = f"{self.api_base}/repos/{owner}/{repo}/contents/{file_path}"
        response = requests.get(url, headers=self.headers)
        
        if response.status_code == 404:
            return None
            
        response.raise_for_status()
        file_data = response.json()
        
        # Decode base64 content
        import base64
        content = base64.b64decode(file_data["content"]).decode("utf-8")
        
        return content
        
    def _verify_pull_request_creation_impl(self, source_branch: str) -> bool:
        """Verify pull request creation in GitHub."""
        owner, repo = self.test_repo.split("/")
        
        url = f"{self.api_base}/repos/{owner}/{repo}/pulls"
        params = {"head": f"{owner}:{source_branch}", "state": "open"}
        
        response = requests.get(url, params=params, headers=self.headers)
        response.raise_for_status()
        
        pull_requests = response.json()
        return len(pull_requests) > 0
        
    def _add_pr_comment_impl(self, pr_number: int, comment: str) -> dict[str, Any]:
        """Add comment to GitHub pull request."""
        owner, repo = self.test_repo.split("/")
        
        url = f"{self.api_base}/repos/{owner}/{repo}/issues/{pr_number}/comments"
        data = {"body": comment}
        
        response = requests.post(url, json=data, headers=self.headers)
        response.raise_for_status()
        
        comment_data = response.json()
        self.logger.info("Added comment to PR #%s", pr_number)
        
        return comment_data
        
    def get_latest_pull_request(self, source_branch: Optional[str] = None) -> Optional[dict[str, Any]]:
        """Get the latest pull request, optionally filtered by source branch."""
        owner, repo = self.test_repo.split("/")
        
        url = f"{self.api_base}/repos/{owner}/{repo}/pulls"
        params = {"state": "open", "sort": "created", "direction": "desc"}
        
        if source_branch:
            params["head"] = f"{owner}:{source_branch}"
            
        response = requests.get(url, params=params, headers=self.headers)
        response.raise_for_status()
        
        pull_requests = response.json()
        return pull_requests[0] if pull_requests else None
        
    def _create_label_if_not_exists(self, label: str) -> None:
        """Create a label if it doesn't exist in GitHub repository."""
        owner, repo = self.test_repo.split("/")
        
        # Check if label exists
        url = f"{self.api_base}/repos/{owner}/{repo}/labels/{label}"
        response = requests.get(url, headers=self.headers)
        
        if response.status_code == 200:
            # Label already exists
            return
            
        if response.status_code != 404:
            response.raise_for_status()
            
        # Create the label
        url = f"{self.api_base}/repos/{owner}/{repo}/labels"
        data = {
            "name": label,
            "color": "0052cc",  # Blue color
            "description": f"Label for coding agent: {label}",
        }
        
        response = requests.post(url, json=data, headers=self.headers)
        if response.status_code != 422:  # 422 means label already exists
            response.raise_for_status()
            
        self.logger.info("Created label: %s", label)