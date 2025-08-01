from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class TaskKey(ABC):
    @abstractmethod
    def to_dict(self) -> dict[str, Any]:
        pass

    @classmethod
    @abstractmethod
    def from_dict(cls, d: dict[str, Any]) -> TaskKey:
        pass


class GitHubIssueTaskKey(TaskKey):
    def __init__(self, owner: str, repo: str, number: int) -> None:
        self.owner = owner
        self.repo = repo
        self.number = number

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "github_issue",
            "owner": self.owner,
            "repo": self.repo,
            "number": self.number,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> GitHubIssueTaskKey:
        return cls(d["owner"], d["repo"], d["number"])


class GitHubPullRequestTaskKey(TaskKey):
    def __init__(self, owner: str, repo: str, number: int) -> None:
        self.owner = owner
        self.repo = repo
        self.number = number

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "github_pull_request",
            "owner": self.owner,
            "repo": self.repo,
            "number": self.number,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> GitHubPullRequestTaskKey:
        return cls(d["owner"], d["repo"], d["number"])


class GitLabIssueTaskKey(TaskKey):
    def __init__(self, project_id: int | str, issue_iid: int | str) -> None:
        self.project_id = project_id
        self.issue_iid = issue_iid

    def to_dict(self) -> dict[str, Any]:
        return {"type": "gitlab_issue", "project_id": self.project_id, "issue_iid": self.issue_iid}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> GitLabIssueTaskKey:
        return cls(d["project_id"], d["issue_iid"])


class GitLabMergeRequestTaskKey(TaskKey):
    def __init__(self, project_id: int | str, mr_iid: int | str) -> None:
        self.project_id = project_id
        self.mr_iid = mr_iid

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "gitlab_merge_request",
            "project_id": self.project_id,
            "mr_iid": self.mr_iid,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> GitLabMergeRequestTaskKey:
        return cls(d["project_id"], d["mr_iid"])
