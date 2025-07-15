"""GitLab-specific implementation of real integration test framework."""
from __future__ import annotations

import base64
import os
from typing import Any

import requests

from .base_framework import RealIntegrationTestFramework

# HTTP timeout constant for security
REQUEST_TIMEOUT = 30
# HTTP status constants
HTTP_NOT_FOUND = 404


class GitLabRealIntegrationFramework(RealIntegrationTestFramework):
    """GitLab-specific real integration test framework."""

    def __init__(self) -> None:
        """Initialize GitLab test framework."""
        super().__init__("gitlab")
        self.api_base = os.environ.get("GITLAB_API_URL", "https://gitlab.com/api/v4")
        gitlab_token = (
            os.environ.get("GITLAB_PERSONAL_ACCESS_TOKEN")
            or os.environ.get("GITLAB_TOKEN")
        )
        self.headers = {
            "Authorization": f"Bearer {gitlab_token}",
            "Content-Type": "application/json",
        }

    def _create_issue_impl(self, title: str, body: str, labels: list[str]) -> dict[str, Any]:
        """Create a GitLab issue."""
        url = f"{self.api_base}/projects/{self.test_project_id}/issues"
        data = {
            "title": title,
            "description": body,
            "labels": ",".join(labels),
        }

        response = requests.post(url, json=data, headers=self.headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()

        issue_data = response.json()
        self.logger.info("Created GitLab issue #%s: %s", issue_data["iid"], title)

        return issue_data

    def _close_issue(self, issue_iid: int) -> None:
        """Close a GitLab issue."""
        url = f"{self.api_base}/projects/{self.test_project_id}/issues/{issue_iid}"
        data = {"state_event": "close"}

        response = requests.put(url, json=data, headers=self.headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()

        self.logger.info("Closed GitLab issue #%s", issue_iid)

    def _get_issue(self, issue_iid: int) -> dict[str, Any]:
        """Get GitLab issue data."""
        url = f"{self.api_base}/projects/{self.test_project_id}/issues/{issue_iid}"
        response = requests.get(url, headers=self.headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()

        return response.json()

    def _verify_file_creation_impl(self, file_path: str, expected_content: str | None) -> bool:
        """Verify file creation in GitLab repository."""
        content = self._get_file_content(file_path)
        if not content:
            return False

        if expected_content:
            return expected_content in content

        return True

    def _get_file_content(self, file_path: str) -> str | None:
        """Get file content from GitLab repository."""
        url = (
            f"{self.api_base}/projects/{self.test_project_id}/repository/files/"
            f"{file_path.replace('/', '%2F')}"
        )
        params = {"ref": "main"}

        response = requests.get(url, params=params, headers=self.headers, timeout=REQUEST_TIMEOUT)

        if response.status_code == HTTP_NOT_FOUND:
            return None

        response.raise_for_status()
        file_data = response.json()

        # Decode base64 content
        return base64.b64decode(file_data["content"]).decode("utf-8")


    def _verify_pull_request_creation_impl(self, source_branch: str) -> bool:
        """Verify merge request creation in GitLab."""
        url = f"{self.api_base}/projects/{self.test_project_id}/merge_requests"
        params = {"source_branch": source_branch, "state": "opened"}

        response = requests.get(url, params=params, headers=self.headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()

        merge_requests = response.json()
        return len(merge_requests) > 0

    def _add_pr_comment_impl(self, mr_iid: int, comment: str) -> dict[str, Any]:
        """Add comment to GitLab merge request."""
        url = f"{self.api_base}/projects/{self.test_project_id}/merge_requests/{mr_iid}/notes"
        data = {"body": comment}

        response = requests.post(url, json=data, headers=self.headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()

        comment_data = response.json()
        self.logger.info("Added comment to MR #%s", mr_iid)

        return comment_data

    def get_latest_merge_request(self, source_branch: str | None = None) -> dict[str, Any] | None:
        """Get the latest merge request, optionally filtered by source branch."""
        url = f"{self.api_base}/projects/{self.test_project_id}/merge_requests"
        params = {"state": "opened", "order_by": "created_at", "sort": "desc"}

        if source_branch:
            params["source_branch"] = source_branch

        response = requests.get(url, params=params, headers=self.headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()

        merge_requests = response.json()
        return merge_requests[0] if merge_requests else None

    def _create_label_if_not_exists(self, label: str) -> None:
        """Create a label if it doesn't exist in GitLab project."""
        # Get existing labels
        url = f"{self.api_base}/projects/{self.test_project_id}/labels"
        response = requests.get(url, headers=self.headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()

        existing_labels = response.json()
        label_names = [label["name"] for label in existing_labels]

        if label in label_names:
            # Label already exists
            return

        # Create the label
        data = {
            "name": label,
            "color": "#0052cc",  # Blue color
            "description": f"Label for coding agent: {label}",
        }

        response = requests.post(url, json=data, headers=self.headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()

        self.logger.info("Created label: %s", label)
