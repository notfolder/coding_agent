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
        super().__init__()
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
        # 空のbodyを除外
        all_comments = [
            comment.get("body", "")
            for comment in self.mcp_client.call_tool("get_issue_comments", args)
            if comment.get("body", "").strip()
        ]
        
        # 最新コメントを主要依頼、それ以前を参考情報として分離
        latest_comment = all_comments[-1] if all_comments else None
        previous_comments = all_comments[:-1] if len(all_comments) > 1 else []
        
        prompt_parts = [
            f"ISSUE: {{'title': '{self.issue.get('title', '')}', "
            f"'body': '{self.issue.get('body', '')}', "
            f"'owner': '{self.issue.get('owner', '')}', "
            f"'repo': '{self.issue.get('repo', '')}'}}"
            f"'issue_number': '{self.issue.get('number', '')}'}}"
        ]
        
        if previous_comments:
            prompt_parts.append(f"\n\nREFERENCE_COMMENTS (参考情報): {previous_comments}")
        
        if latest_comment:
            prompt_parts.append(f"\n\nLATEST_REQUEST (最新の依頼): {latest_comment}")
        elif not all_comments:
            # コメントがない場合はIssue本文が主要依頼
            prompt_parts.append("\n\n(主要依頼はIssue本文を参照)")
        
        return "".join(prompt_parts)

    def comment(self, text: str, *, mention: bool = False) -> dict[str, Any] | None:
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
        return self.mcp_client.call_tool("add_issue_comment", args)

    def update_comment(self, comment_id: int | str, text: str) -> None:
        """Update an existing issue comment."""
        self.github_client.update_issue_comment(
            self.config["github"]["owner"],
            self.issue["repo"],
            int(comment_id),
            text,
        )

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

    def add_label(self, label: str) -> None:
        """Issueにラベルを追加する."""
        if label not in self.labels:
            self.labels.append(label)
            self.issue["labels"] = self.labels
            args = {
                "owner": self.config["github"]["owner"],
                "repo": self.issue["repo"],
                "issue_number": self.issue["number"],
                "labels": self.labels,
            }
            self.mcp_client.call_tool("update_issue", args)

    def remove_label(self, label: str) -> None:
        """Issueからラベルを削除する."""
        if label in self.labels:
            self.labels.remove(label)
            self.issue["labels"] = self.labels
            args = {
                "owner": self.config["github"]["owner"],
                "repo": self.issue["repo"],
                "issue_number": self.issue["number"],
                "labels": self.labels,
            }
            self.mcp_client.call_tool("update_issue", args)

    def get_user(self) -> str | None:
        """Issueの作成者のユーザー名を取得する."""
        return self.issue.get("user", {}).get("login")

    @property
    def title(self) -> str:
        """Issueのタイトルを取得する."""
        return self.issue.get("title", "")

    @property
    def body(self) -> str:
        """Issueの本文を取得する."""
        return self.issue.get("body", "")

    def get_assignees(self) -> list[str]:
        """Issueにアサインされているユーザー名のリストを取得する."""
        assignees = self.issue.get("assignees", [])
        return [a.get("login", "") for a in assignees if a.get("login")]

    def refresh_assignees(self) -> list[str]:
        """APIからアサイン情報を再取得して返す."""
        # Fetch latest issue data from GitHub API
        args = {
            "owner": self.config["github"]["owner"],
            "repo": self.issue["repo"],
            "issue_number": self.issue["number"],
        }
        updated_issue = self.mcp_client.call_tool("get_issue", args)
        
        # Update internal state
        self.issue["assignees"] = updated_issue.get("assignees", [])
        
        return self.get_assignees()

    def get_comments(self) -> list[dict[str, Any]]:
        """Issueの全コメントを取得する.

        Returns:
            コメント情報のリスト
        """
        args = {
            "owner": self.config["github"]["owner"],
            "repo": self.issue["repo"],
            "issue_number": self.issue["number"],
        }
        raw_comments = self.mcp_client.call_tool("get_issue_comments", args)
        
        # 標準形式に変換
        comments = []
        for comment in raw_comments:
            comments.append({
                "id": comment.get("id"),
                "author": comment.get("user", {}).get("login", ""),
                "body": comment.get("body", ""),
                "created_at": comment.get("created_at", ""),
                "updated_at": comment.get("updated_at"),
            })
        
        return comments


class TaskGitHubPullRequest(Task):
    def __init__(
        self,
        pr: dict[str, Any],
        mcp_client: MCPToolClient,
        github_client: GithubClient,
        config: dict[str, Any],
    ) -> None:
        super().__init__()
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
        all_comments = self.github_client.get_pull_request_comments(
            owner=self.pr["owner"], repo=self.pr["repo"], pull_number=self.pr["number"],
        )
        
        # 空のコメントを除外
        all_comments = [
            comment for comment in all_comments
            if (comment.strip() if isinstance(comment, str) else comment.get("body", "").strip())
        ]
        
        # 最新コメントを主要依頼、それ以前を参考情報として分離
        latest_comment = all_comments[-1] if all_comments else None
        previous_comments = all_comments[:-1] if len(all_comments) > 1 else []
        
        pr_info = {
            "pull_request": {
                "title": self.pr.get("title", ""),
                "body": self.pr.get("body", ""),
                "owner": self.pr.get("owner", ""),
                "repo": self.pr.get("repo", ""),
                "pullNumber": self.pr.get("number", ""),
                "branch": self.pr.get("head", {}).get("ref", ""),
            },
        }
        
        prompt_parts = [f"PULL_REQUEST: {json.dumps(pr_info, ensure_ascii=False)}"]
        
        if previous_comments:
            prompt_parts.append(f"\n\nREFERENCE_COMMENTS (参考情報): {json.dumps(previous_comments, ensure_ascii=False)}")
        
        if latest_comment:
            prompt_parts.append(f"\n\nLATEST_REQUEST (最新の依頼): {json.dumps(latest_comment, ensure_ascii=False)}")
        elif not all_comments:
            # コメントがない場合はPR本文が主要依頼
            prompt_parts.append("\n\n(主要依頼はPull Request本文を参照)")
        
        return "".join(prompt_parts) + "\n"

    def comment(self, text: str, *, mention: bool = False) -> dict[str, Any] | None:
        if mention:
            owner = self.pr.get("owner")
            if owner:
                text = f"@{owner} {text}"
        return self.github_client.add_comment_to_pull_request(
            owner=self.pr["owner"], repo=self.pr["repo"], pull_number=self.pr["number"], body=text,
        )

    def update_comment(self, comment_id: int | str, text: str) -> None:
        """Update an existing pull request comment."""
        self.github_client.update_issue_comment(
            self.pr["owner"],
            self.pr["repo"],
            int(comment_id),
            text,
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

    def add_label(self, label: str) -> None:
        """PRにラベルを追加する."""
        if label not in self.labels:
            self.labels.append(label)
            self.pr["labels"] = self.labels
            args = {
                "owner": self.config["github"]["owner"],
                "repo": self.pr["repo"],
                "issue_number": self.pr["number"],
                "labels": self.labels,
            }
            self.mcp_client.call_tool("update_issue", args)

    def remove_label(self, label: str) -> None:
        """PRからラベルを削除する."""
        if label in self.labels:
            self.labels.remove(label)
            self.pr["labels"] = self.labels
            args = {
                "owner": self.config["github"]["owner"],
                "repo": self.pr["repo"],
                "issue_number": self.pr["number"],
                "labels": self.labels,
            }
            self.mcp_client.call_tool("update_issue", args)

    def get_user(self) -> str | None:
        """Pull Requestの作成者のユーザー名を取得する."""
        return self.pr.get("user", {}).get("login")

    @property
    def title(self) -> str:
        """Pull Requestのタイトルを取得する."""
        return self.pr.get("title", "")

    @property
    def body(self) -> str:
        """Pull Requestの本文を取得する."""
        return self.pr.get("body", "")

    def get_assignees(self) -> list[str]:
        """Pull Requestにアサインされているユーザー名のリストを取得する."""
        assignees = self.pr.get("assignees", [])
        return [a.get("login", "") for a in assignees if a.get("login")]

    def refresh_assignees(self) -> list[str]:
        """APIからアサイン情報を再取得して返す."""
        # Fetch latest PR data from GitHub API
        updated_pr = self.github_client.get_pull_request(
            owner=self.pr["owner"],
            repo=self.pr["repo"],
            pull_number=self.pr["number"],
        )
        
        # Update internal state
        self.pr["assignees"] = updated_pr.get("assignees", [])
        
        return self.get_assignees()

    def get_comments(self) -> list[dict[str, Any]]:
        """Pull Requestの会話コメントを取得する.

        注: レビューコメント（コード固有）ではなく、
        一般的な会話コメントのみを取得します。

        Returns:
            コメント情報のリスト
        """
        raw_comments = self.github_client.get_pull_request_comments(
            owner=self.pr["owner"],
            repo=self.pr["repo"],
            pull_number=self.pr["number"],
        )
        
        # 標準形式に変換
        comments = []
        for comment in raw_comments:
            comments.append({
                "id": comment.get("id"),
                "author": comment.get("user", {}).get("login", ""),
                "body": comment.get("body", ""),
                "created_at": comment.get("created_at", ""),
                "updated_at": comment.get("updated_at"),
            })
        
        return comments

    @property
    def source_branch(self) -> str | None:
        """Pull Requestのソースブランチ名を取得する.

        Returns:
            ソースブランチ名、取得できない場合はNone
        """
        return self.pr.get("head", {}).get("ref")


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
