import os

import requests


class GitlabClient:
    def __init__(self, token=None, api_url=None) -> None:
        self.token = token or os.environ.get("GITLAB_PERSONAL_ACCESS_TOKEN")
        self.api_url = api_url or os.environ.get("GITLAB_API_URL") or "https://gitlab.com/api/v4"
        if not self.token:
            msg = "GITLAB_PERSONAL_ACCESS_TOKEN is not set"
            raise ValueError(msg)
        self.headers = {
            "PRIVATE-TOKEN": self.token,
            "Content-Type": "application/json",
        }

    # イシュー一覧取得(ラベル指定可)
    def list_issues(self, project_id, labels=None, state="opened", per_page=100):
        url = f"{self.api_url}/projects/{project_id}/issues"
        params = {"state": state, "per_page": per_page}
        if labels:
            params["labels"] = ",".join(labels)
        resp = requests.get(url, headers=self.headers, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    # イシューコメント(ノート)一覧取得
    def list_issue_notes(self, project_id, issue_iid, per_page=100):
        url = f"{self.api_url}/projects/{project_id}/issues/{issue_iid}/notes"
        params = {"per_page": per_page}
        resp = requests.get(url, headers=self.headers, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    # イシューにコメント追加
    def add_issue_note(self, project_id, issue_iid, body):
        url = f"{self.api_url}/projects/{project_id}/issues/{issue_iid}/notes"
        data = {"body": body}
        resp = requests.post(url, headers=self.headers, json=data, timeout=30)
        resp.raise_for_status()
        return resp.json()

    # イシューラベル変更
    def update_issue_labels(self, project_id, issue_iid, labels):
        url = f"{self.api_url}/projects/{project_id}/issues/{issue_iid}"
        data = {"labels": ",".join(labels)}
        resp = requests.put(url, headers=self.headers, json=data, timeout=30)
        resp.raise_for_status()
        return resp.json()

    # マージリクエスト一覧取得(ラベル指定可)
    def list_merge_requests(
        self, project_id, labels=None, assignee=None, state="opened", per_page=100,
    ):
        url = f"{self.api_url}/projects/{project_id}/merge_requests"
        params = {"state": state, "per_page": per_page}
        if labels:
            params["labels"] = ",".join(labels)
        if assignee:
            params["assignee_username"] = assignee
        resp = requests.get(url, headers=self.headers, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    # マージリクエストコメント(ノート)一覧取得
    def list_merge_request_notes(self, project_id, merge_request_iid, per_page=100):
        url = f"{self.api_url}/projects/{project_id}/merge_requests/{merge_request_iid}/notes"
        params = {"per_page": per_page}
        resp = requests.get(url, headers=self.headers, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    # マージリクエストにコメント追加
    def add_merge_request_note(self, project_id, merge_request_iid, body):
        url = f"{self.api_url}/projects/{project_id}/merge_requests/{merge_request_iid}/notes"
        data = {"body": body}
        resp = requests.post(url, headers=self.headers, json=data, timeout=30)
        resp.raise_for_status()
        return resp.json()

    # マージリクエストラベル変更
    def update_merge_request_labels(self, project_id, merge_request_iid, labels):
        url = f"{self.api_url}/projects/{project_id}/merge_requests/{merge_request_iid}"
        data = {"labels": ",".join(labels)}
        resp = requests.put(url, headers=self.headers, json=data, timeout=30)
        resp.raise_for_status()
        return resp.json()

    # マージリクエスト単体取得
    def get_merge_request(self, project_id, mr_iid):
        url = f"{self.api_url}/projects/{project_id}/merge_requests/{mr_iid}"
        resp = requests.get(url, headers=self.headers, timeout=30)
        resp.raise_for_status()
        return resp.json()

    # イシュー検索(インスタンス全体)
    def search_issues(self, query, state="opened", per_page=200):
        url = f"{self.api_url}/search"
        params = {"scope": "issues", "search": query, "state": state, "per_page": per_page}
        resp = requests.get(url, headers=self.headers, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    # マージリクエスト検索(インスタンス全体)
    def search_merge_requests(self, query, state=None, per_page=200):
        url = f"{self.api_url}/search"
        params = {"scope": "merge_requests", "search": query, "per_page": per_page}
        if state:
            params["state"] = state
        resp = requests.get(url, headers=self.headers, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()
