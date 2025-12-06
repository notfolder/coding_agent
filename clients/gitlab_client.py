from __future__ import annotations

import logging
import os
from typing import Any

import requests

logger = logging.getLogger(__name__)


class GitlabClient:
    def __init__(self, token: str, api_url: str = "https://gitlab.com/api/v4") -> None:
        """GitLabクライアントを初期化する.

        Args:
            token: GitLab Personal Access Token（必須）
            api_url: GitLab APIのベースURL（デフォルト: https://gitlab.com/api/v4）

        Raises:
            ValueError: トークンがNoneまたは空文字列の場合

        """
        # トークンが設定されていない場合はエラー
        if not token:
            msg = "GitLab Personal Access Token is required"
            raise ValueError(msg)
        
        self.token = token
        self.api_url = api_url
        self.headers = {
            "PRIVATE-TOKEN": self.token,
            "Content-Type": "application/json",
        }

    def list_issues(
        self,
        project_id: int | str,
        labels: list[str] | None = None,
        state: str = "opened",
        per_page: int = 100,
        max_pages: int = 200,
    ) -> list[dict[str, Any]]:
        url = f"{self.api_url}/projects/{project_id}/issues"
        params: dict[str, Any] = {"state": state}
        if labels:
            params["labels"] = ",".join(labels)
        return self._fetch_paginated_list(url, params, per_page, max_pages)

    def list_issue_notes(
        self,
        project_id: int | str,
        issue_iid: int | str,
        per_page: int = 100,
        max_pages: int = 200,
    ) -> list[dict[str, Any]]:
        url = f"{self.api_url}/projects/{project_id}/issues/{issue_iid}/notes"
        return self._fetch_paginated_list(url, {}, per_page, max_pages)

    def add_issue_note(
        self, project_id: int | str, issue_iid: int | str, body: str,
    ) -> dict[str, Any]:
        url = f"{self.api_url}/projects/{project_id}/issues/{issue_iid}/notes"
        data = {"body": body}
        resp = requests.post(url, headers=self.headers, json=data, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def update_issue_note(
        self, project_id: int | str, issue_iid: int | str, note_id: int | str, body: str,
    ) -> dict[str, Any]:
        """Update an existing issue note.
        
        Args:
            project_id: Project ID
            issue_iid: Issue internal ID
            note_id: Note ID to update
            body: Updated note content
            
        Returns:
            Updated note information
        """
        url = f"{self.api_url}/projects/{project_id}/issues/{issue_iid}/notes/{note_id}"
        data = {"body": body}
        resp = requests.put(url, headers=self.headers, json=data, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def update_issue_labels(
        self, project_id: int | str, issue_iid: int | str, labels: list[str],
    ) -> dict[str, Any]:
        url = f"{self.api_url}/projects/{project_id}/issues/{issue_iid}"
        data = {"labels": ",".join(labels)}
        resp = requests.put(url, headers=self.headers, json=data, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def get_project(self, project_id: int | str) -> dict[str, Any]:
        """Get project information.
        
        Args:
            project_id: Project ID
            
        Returns:
            Project information including path_with_namespace
        """
        url = f"{self.api_url}/projects/{project_id}"
        resp = requests.get(url, headers=self.headers, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def list_merge_requests(
        self,
        project_id: int | str,
        labels: list[str] | None = None,
        assignee: str | None = None,
        state: str = "opened",
        per_page: int = 100,
        max_pages: int = 200,
    ) -> list[dict[str, Any]]:
        url = f"{self.api_url}/projects/{project_id}/merge_requests"
        params: dict[str, Any] = {"state": state}
        if labels:
            params["labels"] = ",".join(labels)
        if assignee:
            params["assignee_username"] = assignee
        return self._fetch_paginated_list(url, params, per_page, max_pages)

    def list_merge_request_notes(
        self,
        project_id: int | str,
        merge_request_iid: int | str,
        per_page: int = 100,
        max_pages: int = 200,
    ) -> list[dict[str, Any]]:
        url = f"{self.api_url}/projects/{project_id}/merge_requests/{merge_request_iid}/notes"
        return self._fetch_paginated_list(url, {}, per_page, max_pages)

    def add_merge_request_note(
        self, project_id: int | str, merge_request_iid: int | str, body: str,
    ) -> dict[str, Any]:
        url = f"{self.api_url}/projects/{project_id}/merge_requests/{merge_request_iid}/notes"
        data = {"body": body}
        resp = requests.post(url, headers=self.headers, json=data, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def update_merge_request_note(
        self, project_id: int | str, merge_request_iid: int | str, note_id: int | str, body: str,
    ) -> dict[str, Any]:
        """Update an existing merge request note.
        
        Args:
            project_id: Project ID
            merge_request_iid: Merge request internal ID
            note_id: Note ID to update
            body: Updated note content
            
        Returns:
            Updated note information
        """
        url = f"{self.api_url}/projects/{project_id}/merge_requests/{merge_request_iid}/notes/{note_id}"
        data = {"body": body}
        resp = requests.put(url, headers=self.headers, json=data, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def update_merge_request_labels(
        self, project_id: int | str, merge_request_iid: int | str, labels: list[str],
    ) -> dict[str, Any]:
        url = f"{self.api_url}/projects/{project_id}/merge_requests/{merge_request_iid}"
        data = {"labels": ",".join(labels)}
        resp = requests.put(url, headers=self.headers, json=data, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def get_merge_request(
        self, project_id: int | str, mr_iid: int | str,
    ) -> dict[str, Any]:
        url = f"{self.api_url}/projects/{project_id}/merge_requests/{mr_iid}"
        resp = requests.get(url, headers=self.headers, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def list_branches(
        self,
        project_id: int | str,
        per_page: int = 100,
        max_pages: int = 200,
    ) -> list[dict[str, Any]]:
        """List all branches in a project.
        
        Args:
            project_id: Project ID
            per_page: Number of items per page
            max_pages: Maximum number of pages to fetch
            
        Returns:
            List of branch information dictionaries
        """
        url = f"{self.api_url}/projects/{project_id}/repository/branches"
        return self._fetch_paginated_list(url, {}, per_page, max_pages)

    def get_user_by_username(
        self, username: str,
    ) -> dict[str, Any] | None:
        """Get user information by username.
        
        Args:
            username: Username to search for
            
        Returns:
            User information dictionary, or None if not found
        """
        url = f"{self.api_url}/users"
        params = {"username": username}
        resp = requests.get(url, headers=self.headers, params=params, timeout=30)
        resp.raise_for_status()
        users = resp.json()
        if isinstance(users, list) and len(users) > 0:
            return users[0]
        return None

    def create_branch(
        self, project_id: int | str, branch_name: str, ref: str,
    ) -> dict[str, Any]:
        """Create a new branch in a project.
        
        Args:
            project_id: Project ID
            branch_name: Name of the new branch
            ref: Branch, commit SHA, or tag name to create the branch from
            
        Returns:
            Created branch information
        """
        url = f"{self.api_url}/projects/{project_id}/repository/branches"
        data = {"branch": branch_name, "ref": ref}
        resp = requests.post(url, headers=self.headers, json=data, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def create_commit(
        self,
        project_id: int | str,
        branch: str,
        commit_message: str,
        actions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Create a commit with multiple file actions.
        
        Args:
            project_id: Project ID
            branch: Branch name to commit to
            commit_message: Commit message
            actions: List of file actions (create, update, delete, etc.)
                Each action should have: action, file_path, content (if needed)
            
        Returns:
            Created commit information
        """
        url = f"{self.api_url}/projects/{project_id}/repository/commits"
        data = {
            "branch": branch,
            "commit_message": commit_message,
            "actions": actions,
        }
        resp = requests.post(url, headers=self.headers, json=data, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def create_merge_request(
        self,
        project_id: int | str,
        source_branch: str,
        target_branch: str,
        title: str,
        description: str | None = None,
        assignee_ids: list[int] | None = None,
        labels: list[str] | None = None,
        draft: bool = False,
    ) -> dict[str, Any]:
        """Create a new merge request.
        
        Args:
            project_id: Project ID
            source_branch: Source branch name
            target_branch: Target branch name
            title: MR title
            description: MR description (optional)
            assignee_ids: List of user IDs to assign (optional)
            labels: List of labels to add (optional)
            draft: Create as draft MR (optional, default: False)
            
        Returns:
            Created merge request information
        """
        url = f"{self.api_url}/projects/{project_id}/merge_requests"
        
        # GitLabではタイトルに"Draft: "または"WIP: "プレフィックスを付けるとドラフトMRになる
        mr_title = title
        if draft and not (title.startswith("Draft: ") or title.startswith("WIP: ")):
            mr_title = f"Draft: {title}"
        
        data: dict[str, Any] = {
            "source_branch": source_branch,
            "target_branch": target_branch,
            "title": mr_title,
        }
        if description:
            data["description"] = description
        if assignee_ids:
            data["assignee_ids"] = assignee_ids
        if labels:
            data["labels"] = ",".join(labels)
        resp = requests.post(url, headers=self.headers, json=data, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def update_merge_request(
        self,
        project_id: int | str,
        merge_request_iid: int | str,
        title: str | None = None,
        description: str | None = None,
        assignee_ids: list[int] | None = None,
        reviewer_ids: list[int] | None = None,
        labels: list[str] | None = None,
    ) -> dict[str, Any]:
        """Update an existing merge request.
        
        Args:
            project_id: Project ID
            merge_request_iid: Merge request internal ID
            title: New title (optional)
            description: New description (optional)
            assignee_ids: List of user IDs to assign (optional)
            reviewer_ids: List of user IDs to request review (optional)
            labels: List of labels (optional)
            
        Returns:
            Updated merge request information
        """
        url = f"{self.api_url}/projects/{project_id}/merge_requests/{merge_request_iid}"
        data: dict[str, Any] = {}
        if title:
            data["title"] = title
        if description:
            data["description"] = description
        if assignee_ids:
            data["assignee_ids"] = assignee_ids
        if reviewer_ids:
            data["reviewer_ids"] = reviewer_ids
        if labels:
            data["labels"] = ",".join(labels)
        resp = requests.put(url, headers=self.headers, json=data, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def delete_branch(
        self, project_id: int | str, branch_name: str,
    ) -> None:
        """Delete a branch from a project.
        
        Args:
            project_id: Project ID
            branch_name: Name of the branch to delete
        """
        url = f"{self.api_url}/projects/{project_id}/repository/branches/{branch_name}"
        resp = requests.delete(url, headers=self.headers, timeout=30)
        resp.raise_for_status()

    def search_issues(
        self,
        query: str,
        state: str = "opened",
        per_page: int = 200,
        max_pages: int = 200,
    ) -> list[dict[str, Any]]:
        url = f"{self.api_url}/search"
        params: dict[str, Any] = {"scope": "issues", "search": query, "state": state}
        return self._fetch_paginated_list(url, params, per_page, max_pages)

    def search_merge_requests(
        self,
        query: str,
        state: str | None = None,
        per_page: int = 200,
        max_pages: int = 200,
    ) -> list[dict[str, Any]]:
        url = f"{self.api_url}/search"
        params: dict[str, Any] = {"scope": "merge_requests", "search": query}
        if state:
            params["state"] = state
        return self._fetch_paginated_list(url, params, per_page, max_pages)

    def _fetch_paginated_list(
        self,
        url: str,
        params: dict[str, Any],
        per_page: int,
        max_pages: int,
    ) -> list[dict[str, Any]]:
        """GitLab APIからページング結果を全件取得するヘルパー."""
        items: list[dict[str, Any]] = []
        page: int = 1
        visited_pages: set[int] = set()

        # X-Next-Pageヘッダーとレスポンス件数を使って次ページを辿る
        while page not in visited_pages and page <= max_pages:
            visited_pages.add(page)
            page_params = dict(params)
            page_params["per_page"] = per_page
            page_params["page"] = page

            try:
                resp = requests.get(url, headers=self.headers, params=page_params, timeout=30)
                resp.raise_for_status()
                payload = resp.json()
            except requests.exceptions.RequestException as e:
                logger.error(
                    "GitLab API request failed: url=%s, params=%s, error=%s",
                    url, page_params, e
                )
                raise

            page_items: list[dict[str, Any]]
            if isinstance(payload, list):
                page_items = payload
            elif isinstance(payload, dict) and isinstance(payload.get("items"), list):
                page_items = payload["items"]
            else:
                break

            if not page_items:
                break

            items.extend(page_items)

            next_page_header = resp.headers.get("X-Next-Page")
            if next_page_header:
                try:
                    next_page = int(next_page_header)
                except ValueError:
                    break
                if next_page <= 0:
                    break
                page = next_page
                continue

            page += 1

        return items
