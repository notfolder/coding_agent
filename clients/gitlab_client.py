from __future__ import annotations

import os
from typing import Any

import requests


class GitlabClient:
    def __init__(self, token: str | None = None, api_url: str | None = None) -> None:
        self.token = token or os.environ.get("GITLAB_PERSONAL_ACCESS_TOKEN")
        self.api_url = api_url or os.environ.get("GITLAB_API_URL") or "https://gitlab.com/api/v4"
        if not self.token:
            msg = "GITLAB_PERSONAL_ACCESS_TOKEN is not set"
            raise ValueError(msg)
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
    ) -> list[dict[str, Any]]:
        url = f"{self.api_url}/projects/{project_id}/issues"
        params = {"state": state, "per_page": per_page}
        if labels:
            params["labels"] = ",".join(labels)
        resp = requests.get(url, headers=self.headers, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def list_issue_notes(
        self, project_id: int | str, issue_iid: int | str, per_page: int = 100,
    ) -> list[dict[str, Any]]:
        url = f"{self.api_url}/projects/{project_id}/issues/{issue_iid}/notes"
        params = {"per_page": per_page}
        resp = requests.get(url, headers=self.headers, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

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
    ) -> list[dict[str, Any]]:
        url = f"{self.api_url}/projects/{project_id}/merge_requests"
        params = {"state": state, "per_page": per_page}
        if labels:
            params["labels"] = ",".join(labels)
        if assignee:
            params["assignee_username"] = assignee
        resp = requests.get(url, headers=self.headers, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def list_merge_request_notes(
        self, project_id: int | str, merge_request_iid: int | str, per_page: int = 100,
    ) -> list[dict[str, Any]]:
        url = f"{self.api_url}/projects/{project_id}/merge_requests/{merge_request_iid}/notes"
        params = {"per_page": per_page}
        resp = requests.get(url, headers=self.headers, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

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

    def search_issues(
        self, query: str, state: str = "opened", per_page: int = 200,
    ) -> list[dict[str, Any]]:
        url = f"{self.api_url}/search"
        params = {"scope": "issues", "search": query, "state": state, "per_page": per_page}
        resp = requests.get(url, headers=self.headers, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def search_merge_requests(
        self, query: str, state: str | None = None, per_page: int = 200,
    ) -> list[dict[str, Any]]:
        url = f"{self.api_url}/search"
        params = {"scope": "merge_requests", "search": query, "per_page": per_page}
        if state:
            params["state"] = state
        resp = requests.get(url, headers=self.headers, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()
