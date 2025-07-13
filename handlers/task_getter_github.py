from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from clients.github_client import GithubClient

from .task import Task
from .task_getter import TaskGetter
from .task_key import GitHubIssueTaskKey, GitHubPullRequestTaskKey

if TYPE_CHECKING:
    from clients.mcp_tool_client import MCPToolClient


class TaskGitHubIssue(Task):
    def __init__(
        self,
        issue: dict[str, Any],
        mcp_client: MCPToolClient,
        github_client: GithubClient,
        config: dict[str, Any],
    ) -> None:
        self.issue = issue
        self.issue["repo"] = issue["repository_url"].split("/")[-1]
        self.issue["owner"] = issue["repository_url"].split("/")[-2]
        self.mcp_client = mcp_client
        self.github_client = github_client
        self.config = config
        self.labels = [label.get("name", "") for label in issue.get("labels", [])]

    def prepare(self) -> None:
        # ラベル付け変更
        self.labels.remove(self.config["github"]["bot_label"]) if self.config["github"][
            "bot_label"
        ] in self.labels else None
        self.labels.append(self.config["github"]["processing_label"]) if self.config["github"][
            "processing_label"
        ] not in self.labels else None
        self.issue["labels"] = self.labels
        args = {
            "owner": self.config["github"]["owner"],
            "repo": self.issue["repo"],
            "issue_number": self.issue["number"],
            "labels": self.labels,
        }
        self.mcp_client.call_tool("update_issue", args)

    def get_prompt(self) -> str:
        # issue内容・コメント取得
        args = {
            "owner": self.config["github"]["owner"],
            "repo": self.issue["repo"],
            "issue_number": self.issue["number"],
        }
        comments = [
            comment.get("body", "")
            for comment in self.mcp_client.call_tool("get_issue_comments", args)
        ]
        return (
            f"ISSUE: {{'title': '{self.issue.get('title', '')}', "
            f"'body': '{self.issue.get('body', '')}', "
            f"'owner': '{self.issue.get('owner', '')}', "
            f"'repo': '{self.issue.get('repo', '')}'}}\n"
            f"'issue_number': '{self.issue.get('number', '')}'}}\n"
            f"COMMENTS: {comments}"
        )

    def comment(self, text: str, *, mention: bool = False) -> None:
        if mention:
            owner = self.issue.get("owner")
            if owner:
                text = f"@{owner} {text}"
        args = {
            "owner": self.config["github"]["owner"],
            "repo": self.issue["repo"],
            "issue_number": self.issue["number"],
            "body": text,
        }
        self.mcp_client.call_tool("add_issue_comment", args)

    def finish(self) -> None:
        # ラベル付け変更
        label = self.config["github"]["processing_label"]
        self.labels.remove(label) if label in self.labels else None
        self.labels.append(self.config["github"]["done_label"])
        self.issue["labels"] = self.labels
        args = {
            "owner": self.config["github"]["owner"],
            "repo": self.issue["repo"],
            "issue_number": self.issue["number"],
            "labels": self.labels,
        }
        self.mcp_client.call_tool("update_issue", args)

    def get_task_key(self) -> GitHubIssueTaskKey:
        return GitHubIssueTaskKey(self.issue["owner"], self.issue["repo"], self.issue["number"])

    def check(self) -> bool:
        return self.config["github"]["processing_label"] in self.labels


class TaskGitHubPullRequest(Task):
    def __init__(
        self,
        pr: dict[str, Any],
        mcp_client: MCPToolClient,
        github_client: GithubClient,
        config: dict[str, Any],
    ) -> None:
        self.pr = pr
        repository_url = pr.get("repository_url")
        if repository_url is None:
            repository_url = pr.get("base", {}).get("repo", {}).get("html_url", "")
        self.pr["repo"] = repository_url.split("/")[-1]
        self.pr["owner"] = repository_url.split("/")[-2]
        self.mcp_client = mcp_client
        self.github_client = github_client
        self.config = config
        self.labels = [
            label.get("name", "") if isinstance(label, dict) else label
            for label in pr.get("labels", [])
        ]  # ラベルが辞書型であることを確認

    def prepare(self) -> None:
        # ラベル付け変更
        self.labels = list(set(self.labels))
        self.labels.append(self.config["github"]["processing_label"]) if self.config["github"][
            "processing_label"
        ] not in self.labels else None
        if self.config["github"]["bot_label"] in self.labels:
            self.labels.remove(self.config["github"]["bot_label"])
        self.pr["labels"] = self.labels
        self.github_client.update_pull_request_labels(
            self.pr["owner"], self.pr["repo"], self.pr["number"], self.labels,
        )

    def get_prompt(self) -> str:
        comments = self.github_client.get_pull_request_comments(
            owner=self.pr["owner"], repo=self.pr["repo"], pull_number=self.pr["number"],
        )
        pr_info = {
            "pull_request": {
                "title": self.pr.get("title", ""),
                "body": self.pr.get("body", ""),
                "owner": self.pr.get("owner", ""),
                "repo": self.pr.get("repo", ""),
                "pullNumber": self.pr.get("number", ""),
                "branch": self.pr.get("head", {}).get("ref", ""),
            },
            "comments": comments,
        }
        return f"PULL_REQUEST: {json.dumps(pr_info, ensure_ascii=False)}\n"

    def comment(self, text: str, *, mention: bool = False) -> None:
        if mention:
            owner = self.pr.get("owner")
            if owner:
                text = f"@{owner} {text}"
        self.github_client.add_comment_to_pull_request(
            owner=self.pr["owner"], repo=self.pr["repo"], pull_number=self.pr["number"], body=text,
        )

    def finish(self) -> None:
        label = self.config["github"]["processing_label"]
        if label in self.labels:
            self.labels.remove(label)
        self.labels.append(self.config["github"]["done_label"])
        self.pr["labels"] = self.labels
        self.github_client.update_pull_request_labels(
            self.pr["owner"], self.pr["repo"], self.pr["number"], self.labels,
        )

    def get_task_key(self) -> GitHubPullRequestTaskKey:
        return GitHubPullRequestTaskKey(self.pr["owner"], self.pr["repo"], self.pr["number"])

    def check(self) -> bool:
        return self.config["github"]["processing_label"] in self.labels


class TaskGetterFromGitHub(TaskGetter):
    def __init__(self, config: dict[str, Any], mcp_clients: dict[str, MCPToolClient]) -> None:
        self.config = config
        self.mcp_client = mcp_clients["github"]
        self.github_client = GithubClient()

    def get_task_list(self) -> list[Task]:
        # MCPサーバーでissue検索
        query = (
            f'label:"{self.config["github"]["bot_label"]}" {self.config["github"].get("query", "")}'
        )
        assignee = self.config["github"].get("assignee")
        if assignee:
            query += f" assignee:{assignee}"
        else:
            query += "  author:@me"
        issues = self.github_client.search_issues(query)
        tasks = [
            TaskGitHubIssue(issue, self.mcp_client, self.github_client, self.config)
            for issue in issues
        ]

        query = (
            f'label:"{self.config["github"]["bot_label"]}" {self.config["github"].get("query", "")}'
        )
        if assignee:
            query += f" assignee:{assignee}"
        else:
            query += "  author:@me"
        prs = self.github_client.search_pull_requests(query)
        pr_tasks = [
            TaskGitHubPullRequest(pr, self.mcp_client, self.github_client, self.config)
            for pr in prs
        ]
        tasks.extend(pr_tasks)

        return tasks

    def from_task_key(self, task_key_dict: dict[str, Any]) -> Task | None:
        ttype = task_key_dict.get("type")
        if ttype == "github_issue":
            task_key = GitHubIssueTaskKey.from_dict(task_key_dict)
            issue = self.mcp_client.call_tool(
                "get_issue",
                {"owner": task_key.owner, "repo": task_key.repo, "issue_number": task_key.number},
            )
            return TaskGitHubIssue(issue, self.mcp_client, self.github_client, self.config)
        if ttype == "github_pull_request":
            task_key = GitHubPullRequestTaskKey.from_dict(task_key_dict)
            pr = self.github_client.get_pull_request(
                owner=task_key.owner, repo=task_key.repo, pull_number=task_key.number,
            )
            return TaskGitHubPullRequest(pr, self.mcp_client, self.github_client, self.config)
        return None
