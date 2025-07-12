from abc import ABC, abstractmethod


class TaskKey(ABC):
    @abstractmethod
    def to_dict(self):
        pass

    @classmethod
    @abstractmethod
    def from_dict(cls, d):
        pass


class GitHubIssueTaskKey(TaskKey):
    def __init__(self, owner, repo, number) -> None:
        self.owner = owner
        self.repo = repo
        self.number = number

    def to_dict(self):
        return {
            "type": "github_issue",
            "owner": self.owner,
            "repo": self.repo,
            "number": self.number,
        }

    @classmethod
    def from_dict(cls, d):
        return cls(d["owner"], d["repo"], d["number"])


class GitHubPullRequestTaskKey(TaskKey):
    def __init__(self, owner, repo, number) -> None:
        self.owner = owner
        self.repo = repo
        self.number = number

    def to_dict(self):
        return {
            "type": "github_pull_request",
            "owner": self.owner,
            "repo": self.repo,
            "number": self.number,
        }

    @classmethod
    def from_dict(cls, d):
        return cls(d["owner"], d["repo"], d["number"])


class GitLabIssueTaskKey(TaskKey):
    def __init__(self, project_id, issue_iid) -> None:
        self.project_id = project_id
        self.issue_iid = issue_iid

    def to_dict(self):
        return {"type": "gitlab_issue", "project_id": self.project_id, "issue_iid": self.issue_iid}

    @classmethod
    def from_dict(cls, d):
        return cls(d["project_id"], d["issue_iid"])


class GitLabMergeRequestTaskKey(TaskKey):
    def __init__(self, project_id, mr_iid) -> None:
        self.project_id = project_id
        self.mr_iid = mr_iid

    def to_dict(self):
        return {
            "type": "gitlab_merge_request",
            "project_id": self.project_id,
            "mr_iid": self.mr_iid,
        }

    @classmethod
    def from_dict(cls, d):
        return cls(d["project_id"], d["mr_iid"])
