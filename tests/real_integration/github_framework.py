"""GitHub固有のリアル統合テストフレームワーク実装."""
from __future__ import annotations

import base64
import os
from typing import Any

import requests

from .base_framework import RealIntegrationTestFramework

# HTTPステータスコード定数
HTTP_OK = 200
HTTP_NOT_FOUND = 404
HTTP_UNPROCESSABLE_ENTITY = 422

# タイムアウト設定
REQUEST_TIMEOUT = 30


class GitHubRealIntegrationFramework(RealIntegrationTestFramework):
    """GitHub固有のリアル統合テストフレームワーク."""

    def __init__(self) -> None:
        """GitHubテストフレームワークを初期化する."""
        super().__init__("github")
        self.api_base = "https://api.github.com"
        github_token = (
            os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN")
            or os.environ.get("GITHUB_TOKEN")
        )
        self.headers = {
            "Authorization": f"token {github_token}",
            "Accept": "application/vnd.github.v3+json",
        }

    def _create_issue_impl(
        self,
        title: str,
        body: str,
        labels: list[str],
        assignee: str | None = None,
    ) -> dict[str, Any]:
        """GitHubイシューを作成する.

        Args:
            title: イシューのタイトル
            body: イシューの本文
            labels: ラベルのリスト
            assignee: アサインするユーザー名(オプション)

        Returns:
            作成されたイシューの詳細を含む辞書

        """
        owner, repo = self.test_repo.split("/")

        url = f"{self.api_base}/repos/{owner}/{repo}/issues"
        data = {
            "title": title,
            "body": body,
            "labels": labels,
        }

        # アサイニーが指定されている場合は追加
        if assignee:
            data["assignees"] = [assignee]

        response = requests.post(url, json=data, headers=self.headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()

        issue_data = response.json()
        self.logger.info("Created GitHub issue #%s: %s", issue_data["number"], title)

        if assignee:
            self.logger.info("Assigned issue #%s to %s", issue_data["number"], assignee)

        return issue_data

    def _close_issue(self, issue_number: int) -> None:
        """GitHubイシューを閉じる."""
        owner, repo = self.test_repo.split("/")

        url = f"{self.api_base}/repos/{owner}/{repo}/issues/{issue_number}"
        data = {"state": "closed"}

        response = requests.patch(url, json=data, headers=self.headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()

        self.logger.info("Closed GitHub issue #%s", issue_number)

    def _get_issue(self, issue_number: int) -> dict[str, Any]:
        """GitHubイシューデータを取得する."""
        owner, repo = self.test_repo.split("/")

        url = f"{self.api_base}/repos/{owner}/{repo}/issues/{issue_number}"
        response = requests.get(url, headers=self.headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()

        return response.json()

    def _verify_file_creation_impl(
        self,
        file_path: str,
        expected_content: str | None,
    ) -> bool:
        """GitHubリポジトリでのファイル作成を確認する."""
        content = self._get_file_content(file_path)
        if not content:
            return False

        if expected_content:
            return expected_content in content

        return True

    def _get_file_content(self, file_path: str) -> str | None:
        """GitHubリポジトリからファイル内容を取得する."""
        owner, repo = self.test_repo.split("/")

        url = f"{self.api_base}/repos/{owner}/{repo}/contents/{file_path}"
        response = requests.get(url, headers=self.headers, timeout=REQUEST_TIMEOUT)

        if response.status_code == HTTP_NOT_FOUND:
            return None

        response.raise_for_status()
        file_data = response.json()

        # base64内容をデコード
        return base64.b64decode(file_data["content"]).decode("utf-8")

    def _verify_pull_request_creation_impl(self, source_branch: str) -> bool:
        """GitHubでのプルリクエスト作成を確認する."""
        owner, repo = self.test_repo.split("/")

        url = f"{self.api_base}/repos/{owner}/{repo}/pulls"
        params = {"head": f"{owner}:{source_branch}", "state": "open"}

        response = requests.get(url, params=params, headers=self.headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()

        pull_requests = response.json()
        return len(pull_requests) > 0

    def _add_pr_comment_impl(self, pr_number: int, comment: str) -> dict[str, Any]:
        """GitHubプルリクエストにコメントを追加する."""
        owner, repo = self.test_repo.split("/")

        url = f"{self.api_base}/repos/{owner}/{repo}/issues/{pr_number}/comments"
        data = {"body": comment}

        response = requests.post(url, json=data, headers=self.headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()

        comment_data = response.json()
        self.logger.info("Added comment to PR #%s", pr_number)

        return comment_data

    def get_latest_pull_request(
        self,
        source_branch: str | None = None,
    ) -> dict[str, Any] | None:
        """最新のプルリクエストを取得する(オプションでソースブランチでフィルタリング)."""
        owner, repo = self.test_repo.split("/")

        url = f"{self.api_base}/repos/{owner}/{repo}/pulls"
        params = {"state": "open", "sort": "created", "direction": "desc"}

        if source_branch:
            params["head"] = f"{owner}:{source_branch}"

        response = requests.get(url, params=params, headers=self.headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()

        pull_requests = response.json()
        return pull_requests[0] if pull_requests else None

    def assign_pull_request(self, pr_number: int, assignee: str) -> bool:
        """GitHubプルリクエストにユーザーをアサインする.

        Args:
            pr_number: プルリクエスト番号
            assignee: アサインするユーザー名

        Returns:
            成功した場合True、失敗した場合False

        """
        if not assignee:
            return False

        owner, repo = self.test_repo.split("/")

        url = f"{self.api_base}/repos/{owner}/{repo}/issues/{pr_number}/assignees"
        data = {"assignees": [assignee]}

        try:
            response = requests.post(url, json=data, headers=self.headers, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            self.logger.info("Assigned PR #%s to %s", pr_number, assignee)
        except requests.RequestException as e:
            self.logger.warning("Failed to assign PR #%s to %s: %s", pr_number, assignee, e)
            return False

        return True

    def _create_label_if_not_exists(self, label: str) -> None:
        """GitHubリポジトリでラベルが存在しない場合は作成する."""
        owner, repo = self.test_repo.split("/")

        # ラベルが存在するかをチェック
        url = f"{self.api_base}/repos/{owner}/{repo}/labels/{label}"
        response = requests.get(url, headers=self.headers, timeout=REQUEST_TIMEOUT)

        if response.status_code == HTTP_OK:
            # ラベルは既に存在する
            return

        if response.status_code != HTTP_NOT_FOUND:
            response.raise_for_status()

        # ラベルを作成
        url = f"{self.api_base}/repos/{owner}/{repo}/labels"
        data = {
            "name": label,
            "color": "0052cc",  # 青色
            "description": f"コーディングエージェント用ラベル: {label}",
        }

        response = requests.post(url, json=data, headers=self.headers, timeout=REQUEST_TIMEOUT)
        # 422はラベルが既に存在することを意味する
        if response.status_code != HTTP_UNPROCESSABLE_ENTITY:
            response.raise_for_status()

        self.logger.info("Created label: %s", label)
