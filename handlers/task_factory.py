from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from .task_key import (
    GitHubIssueTaskKey,
    GitHubPullRequestTaskKey,
    GitLabIssueTaskKey,
    GitLabMergeRequestTaskKey,
    TaskKey,
)

if TYPE_CHECKING:
    from clients.github_client import GithubClient
    from clients.gitlab_client import GitlabClient
    from clients.mcp_tool_client import MCPToolClient

    from .task import Task

from .task_getter_github import TaskGitHubIssue, TaskGitHubPullRequest
from .task_getter_gitlab import TaskGitLabIssue, TaskGitLabMergeRequest


class TaskFactory(ABC):
    @abstractmethod
    def create_task(self, task_key: TaskKey) -> Task | None:
        pass


class GitHubTaskFactory(TaskFactory):
    def __init__(
        self,
        mcp_client: MCPToolClient,
        github_client: GithubClient,
        config: dict[str, Any],
    ) -> None:
        self.mcp_client = mcp_client
        self.github_client = github_client
        self.config = config

    def create_task(self, task_key: TaskKey) -> Task | None:
        if isinstance(task_key, GitHubIssueTaskKey):
            issue = self.mcp_client.call_tool(
                "get_issue",
                {"owner": task_key.owner, "repo": task_key.repo, "issue_number": task_key.number},
            )
            return TaskGitHubIssue(issue, self.mcp_client, self.github_client, self.config)
        if isinstance(task_key, GitHubPullRequestTaskKey):
            pr = self.github_client.get_pull_request(
                owner=task_key.owner, repo=task_key.repo, pull_number=task_key.number,
            )
            return TaskGitHubPullRequest(pr, self.mcp_client, self.github_client, self.config)
        msg = "Unknown task key type for GitHub"
        raise ValueError(msg)


class GitLabTaskFactory(TaskFactory):
    def __init__(
        self,
        mcp_client: MCPToolClient,
        gitlab_client: GitlabClient,
        config: dict[str, Any],
    ) -> None:
        self.mcp_client = mcp_client
        self.gitlab_client = gitlab_client
        self.config = config

    def create_task(self, task_key: TaskKey) -> Task | None:
        if isinstance(task_key, GitLabIssueTaskKey):
            issue = self.mcp_client.call_tool(
                "get_issue", {"project_id": task_key.project_id, "issue_iid": task_key.issue_iid},
            )
            return TaskGitLabIssue(issue, self.mcp_client, self.gitlab_client, self.config)
        if isinstance(task_key, GitLabMergeRequestTaskKey):
            mr = self.gitlab_client.get_merge_request(
                project_id=task_key.project_id, mr_iid=task_key.mr_iid,
            )
            return TaskGitLabMergeRequest(mr, self.mcp_client, self.gitlab_client, self.config)
        msg = "Unknown task key type for GitLab"
        raise ValueError(msg)
