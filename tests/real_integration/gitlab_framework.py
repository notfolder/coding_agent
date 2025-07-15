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

    def _create_issue_impl(
        self,
        title: str,
        body: str,
        labels: list[str],
        assignee: str | None = None,
    ) -> dict[str, Any]:
        """GitLabイシューを作成する.

        Args:
            title: イシューのタイトル
            body: イシューの本文
            labels: ラベルのリスト
            assignee: アサインするユーザー名(オプション)

        Returns:
            作成されたイシューの詳細を含む辞書

        """
        url = f"{self.api_base}/projects/{self.test_project_id}/issues"
        data = {
            "title": title,
            "description": body,
            "labels": ",".join(labels),
        }

        # アサイニーが指定されている場合はユーザーIDを取得して追加
        if assignee:
            assignee_id = self._get_user_id(assignee)
            if assignee_id:
                data["assignee_id"] = assignee_id

        response = requests.post(url, json=data, headers=self.headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()

        issue_data = response.json()
        self.logger.info("Created GitLab issue #%s: %s", issue_data["iid"], title)

        if assignee and assignee_id:
            self.logger.info("Assigned issue #%s to %s", issue_data["iid"], assignee)

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

    def _get_user_id(self, username: str) -> int | None:
        """GitLabユーザー名からユーザーIDを取得する.

        Args:
            username: GitLabユーザー名

        Returns:
            ユーザーID、または見つからない場合はNone

        """
        url = f"{self.api_base}/users"
        params = {"username": username}

        try:
            response = requests.get(
                url, params=params, headers=self.headers, timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            users = response.json()

            if users:
                return users[0]["id"]
        except requests.RequestException as e:
            self.logger.warning("Failed to get user ID for %s: %s", username, e)

        return None

    def assign_merge_request(self, mr_iid: int, assignee: str) -> bool:
        """GitLabマージリクエストにユーザーをアサインする.

        Args:
            mr_iid: マージリクエストのIID
            assignee: アサインするユーザー名

        Returns:
            成功した場合True、失敗した場合False

        """
        if not assignee:
            return False

        assignee_id = self._get_user_id(assignee)
        if not assignee_id:
            return False

        url = f"{self.api_base}/projects/{self.test_project_id}/merge_requests/{mr_iid}"
        data = {"assignee_id": assignee_id}

        try:
            response = requests.put(url, json=data, headers=self.headers, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            self.logger.info("Assigned MR #%s to %s", mr_iid, assignee)
        except requests.RequestException as e:
            self.logger.warning("Failed to assign MR #%s to %s: %s", mr_iid, assignee, e)
            return False

        return True

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

    def _close_all_pull_requests(self) -> None:
        """全てのオープンなマージリクエストを閉じる."""
        # オープンなマージリクエストを全て取得
        url = f"{self.api_base}/projects/{self.test_project_id}/merge_requests"
        params = {"state": "opened", "per_page": 100}

        response = requests.get(url, params=params, headers=self.headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()

        merge_requests = response.json()
        self.logger.info("Found %d open merge requests to close", len(merge_requests))

        for mr in merge_requests:
            mr_iid = mr["iid"]
            try:
                # マージリクエストを閉じる
                close_url = (
                    f"{self.api_base}/projects/{self.test_project_id}/merge_requests/{mr_iid}"
                )
                close_data = {"state_event": "close"}

                close_response = requests.put(
                    close_url, json=close_data, headers=self.headers, timeout=REQUEST_TIMEOUT,
                )
                close_response.raise_for_status()
                self.logger.info("Closed merge request #%d", mr_iid)

            except requests.RequestException as e:
                self.logger.warning("Failed to close merge request #%d: %s", mr_iid, e)

    def _delete_all_branches(self) -> None:
        """メインブランチ以外の全てのブランチを削除する."""
        # 全てのブランチを取得
        url = f"{self.api_base}/projects/{self.test_project_id}/repository/branches"
        params = {"per_page": 100}

        response = requests.get(url, params=params, headers=self.headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()

        branches = response.json()
        main_branches = {"main", "master", "develop"}

        branches_to_delete = [
            branch["name"] for branch in branches
            if branch["name"] not in main_branches
        ]

        self.logger.info(
            "Found %d branches to delete: %s", len(branches_to_delete), branches_to_delete,
        )

        for branch_name in branches_to_delete:
            try:
                # ブランチを削除
                delete_url = (
                    f"{self.api_base}/projects/{self.test_project_id}/repository/branches/"
                    f"{branch_name.replace('/', '%2F')}"
                )

                delete_response = requests.delete(
                    delete_url, headers=self.headers, timeout=REQUEST_TIMEOUT,
                )
                delete_response.raise_for_status()
                self.logger.info("Deleted branch: %s", branch_name)

            except requests.RequestException as e:  # noqa: PERF203
                self.logger.warning("Failed to delete branch %s: %s", branch_name, e)

    def _delete_file(self, file_path: str) -> None:
        """リポジトリからファイルを削除する."""
        try:
            # まずファイルが存在するかチェック
            encoded_file_path = file_path.replace("/", "%2F")
            content_url = (
                f"{self.api_base}/projects/{self.test_project_id}/repository/files/"
                f"{encoded_file_path}"
            )
            content_params = {"ref": "main"}

            content_response = requests.get(
                content_url, params=content_params, headers=self.headers, timeout=REQUEST_TIMEOUT,
            )

            if content_response.status_code == HTTP_NOT_FOUND:
                self.logger.info("File %s does not exist, skipping deletion", file_path)
                return

            content_response.raise_for_status()

            # ファイルを削除
            delete_data = {
                "branch": "main",
                "commit_message": f"Delete {file_path} for test cleanup",
            }

            delete_response = requests.delete(
                content_url, json=delete_data, headers=self.headers, timeout=REQUEST_TIMEOUT,
            )
            delete_response.raise_for_status()
            self.logger.info("Deleted file: %s", file_path)

        except requests.RequestException as e:
            self.logger.warning("Failed to delete file %s: %s", file_path, e)

    def add_label_to_merge_request(self, mr_iid: int, label: str) -> bool:
        """GitLabマージリクエストにラベルを追加する.

        Args:
            mr_iid: マージリクエストのIID
            label: 追加するラベル名

        Returns:
            成功した場合True、失敗した場合False

        """
        if not label:
            return False

        # まずラベルが存在することを確認
        self._create_label_if_not_exists(label)

        # マージリクエストにラベルを追加
        url = f"{self.api_base}/projects/{self.test_project_id}/merge_requests/{mr_iid}"
        data = {"add_labels": label}

        try:
            response = requests.put(url, json=data, headers=self.headers, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            self.logger.info("Added label '%s' to MR #%s", label, mr_iid)
        except requests.RequestException as e:
            self.logger.warning("Failed to add label '%s' to MR #%s: %s", label, mr_iid, e)
            return False

        return True
