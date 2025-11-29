from __future__ import annotations

from typing import TYPE_CHECKING, Any

from clients.gitlab_client import GitlabClient

from .task import Task
from .task_getter import TaskGetter
from .task_key import GitLabIssueTaskKey, GitLabMergeRequestTaskKey

if TYPE_CHECKING:
    from clients.mcp_tool_client import MCPToolClient


class TaskGitLabIssue(Task):
    def __init__(
        self,
        issue: dict[str, Any],
        mcp_client: MCPToolClient,
        gitlab_client: GitlabClient,
        config: dict[str, Any],
    ) -> None:
        super().__init__()
        self.issue = issue
        self.project_id = issue.get("project_id")
        self.issue_iid = issue.get("iid")
        self.mcp_client = mcp_client
        self.gitlab_client = gitlab_client
        self.config = config

    def _refresh_issue(self) -> None:
        """最新のIssue情報を取得してself.issueを更新する."""
        args = {"project_id": f"{self.project_id}", "issue_iid": self.issue_iid}
        self.issue = self.mcp_client.call_tool("get_issue", args)

    def prepare(self) -> None:
        # 最新のIssue情報を取得
        self._refresh_issue()
        
        # ラベル付け変更: bot_label → processing_label
        labels = self.issue.get("labels", [])
        if self.config["gitlab"]["bot_label"] in labels:
            labels.remove(self.config["gitlab"]["bot_label"])
        if self.config["gitlab"]["processing_label"] not in labels:
            labels.append(self.config["gitlab"]["processing_label"])
        args = {"project_id": f"{self.project_id}", "issue_iid": self.issue_iid, "labels": labels}
        self.issue["labels"] = labels
        self.mcp_client.call_tool("update_issue", args)

    def get_prompt(self) -> str:
        # issue本体取得（最新情報を取得してself.issueに代入）
        self._refresh_issue()
        discussions = self._fetch_issue_discussions()
        comments = [
            [note.get("body", "") for note in discussion.get("notes", [])]
            for discussion in discussions
        ]
        return (
            f"ISSUE: {{'title': '{self.issue.get('title', '')}', "
            f"'description': '{self.issue.get('description', '')}', "
            f"'project_id': '{self.issue.get('project_id', '')}'\n"
            f"'issue_iid': '{self.issue.get('iid', '')}'}}\n"
            f"COMMENTS: {comments}"
        )

    def comment(self, text: str, *, mention: bool = False) -> dict[str, Any] | None:
        if mention:
            owner = self.issue.get("author", {}).get("username")
            if owner:
                text = f"@{owner} {text}"
        args = {
            "project_id": f"{self.project_id}",
            "noteable_type": "issue",
            "noteable_iid": self.issue_iid,
            "body": text,
        }
        return self.mcp_client.call_tool("create_note", args)

    def update_comment(self, comment_id: int | str, text: str) -> None:
        """Update an existing issue comment."""
        self.gitlab_client.update_issue_note(
            self.project_id,
            self.issue_iid,
            comment_id,
            text,
        )

    def finish(self) -> None:
        # 最新のIssue情報を取得
        self._refresh_issue()
        # ラベル付け変更: processing_label → done_label
        labels = self.issue.get("labels", [])
        if self.config["gitlab"]["processing_label"] in labels:
            labels.remove(self.config["gitlab"]["processing_label"])
        if self.config["gitlab"]["done_label"] not in labels:
            labels.append(self.config["gitlab"]["done_label"])
        args = {"project_id": f"{self.project_id}", "issue_iid": self.issue_iid, "labels": labels}
        self.issue["labels"] = labels
        self.mcp_client.call_tool("update_issue", args)

    def get_task_key(self) -> GitLabIssueTaskKey:
        return GitLabIssueTaskKey(self.project_id, self.issue_iid)

    def check(self) -> bool:
        # 最新のIssue情報を取得
        self._refresh_issue()
        return self.config["gitlab"]["processing_label"] in self.issue.get("labels", [])

    def add_label(self, label: str) -> None:
        """Issueにラベルを追加する."""
        labels = self.issue.get("labels", [])
        if label not in labels:
            labels.append(label)
            args = {"project_id": f"{self.project_id}", "issue_iid": self.issue_iid, "labels": labels}
            self.issue["labels"] = labels
            self.mcp_client.call_tool("update_issue", args)

    def remove_label(self, label: str) -> None:
        """Issueからラベルを削除する."""
        labels = self.issue.get("labels", [])
        if label in labels:
            labels.remove(label)
            args = {"project_id": f"{self.project_id}", "issue_iid": self.issue_iid, "labels": labels}
            self.issue["labels"] = labels
            self.mcp_client.call_tool("update_issue", args)

    def get_user(self) -> str | None:
        """Issueの作成者のユーザー名を取得する."""
        return self.issue.get("author", {}).get("username")

    @property
    def title(self) -> str:
        """Issueのタイトルを取得する."""
        return self.issue.get("title", "")

    @property
    def body(self) -> str:
        """Issueの本文を取得する."""
        return self.issue.get("description", "")

    def get_assignees(self) -> list[str]:
        """Issueにアサインされているユーザー名のリストを取得する."""
        # GitLabでは assignees (複数) と assignee (単一) の両方がある
        assignees = self.issue.get("assignees", [])
        if assignees:
            return [a.get("username", "") for a in assignees if a.get("username")]
        
        # assignees が空の場合は assignee を確認
        assignee = self.issue.get("assignee")
        if assignee and assignee.get("username"):
            return [assignee.get("username")]
        
        return []

    def refresh_assignees(self) -> list[str]:
        """APIからアサイン情報を再取得して返す."""
        # Fetch latest issue data from GitLab API
        args = {"project_id": f"{self.project_id}", "issue_iid": self.issue_iid}
        updated_issue = self.mcp_client.call_tool("get_issue", args)
        
        # Update internal state
        self.issue["assignees"] = updated_issue.get("assignees", [])
        self.issue["assignee"] = updated_issue.get("assignee")
        
        return self.get_assignees()

    def get_comments(self) -> list[dict[str, Any]]:
        """Issueの全コメントを取得する.

        Returns:
            コメント情報のリスト
        """
        discussions = self._fetch_issue_discussions()

        # GitLabのdiscussion構造からコメントを抽出し、標準形式に変換
        comments: list[dict[str, Any]] = []
        for discussion in discussions:
            for note in discussion.get("notes", []):
                comments.append({
                    "id": note.get("id"),
                    "author": note.get("author", {}).get("username", ""),
                    "body": note.get("body", ""),
                    "created_at": note.get("created_at", ""),
                    "updated_at": note.get("updated_at"),
                })

        return comments

    def _fetch_issue_discussions(self, *, per_page: int = 100, max_pages: int = 200) -> list[dict[str, Any]]:
        """Issueに紐づくディスカッションを全ページ取得する."""
        configured_per_page = self.config.get("gitlab", {}).get("discussion_per_page")
        if isinstance(configured_per_page, int) and configured_per_page > 0:
            per_page = configured_per_page

        configured_max_pages = self.config.get("gitlab", {}).get("discussion_max_pages")
        if isinstance(configured_max_pages, int) and configured_max_pages > 0:
            max_pages = configured_max_pages

        all_discussions: list[dict[str, Any]] = []
        page: int = 1
        visited_pages: set[int] = set()

        # GitLab MCPツールのページネーションを辿りながら全ディスカッションを収集
        while page not in visited_pages and page <= max_pages:
            visited_pages.add(page)
            note_args = {
                "project_id": f"{self.project_id}",
                "issue_iid": self.issue_iid,
                "page": page,
                "per_page": per_page,
            }
            response = self.mcp_client.call_tool("list_issue_discussions", note_args)
            discussions: list[dict[str, Any]] = []

            if isinstance(response, dict):
                discussions = response.get("items", []) or []
            elif isinstance(response, list):
                discussions = response

            if not discussions:
                break

            all_discussions.extend(discussions)

            next_page = self._determine_next_page(response, page)
            if next_page is None:
                if len(discussions) < per_page:
                    break
                page += 1
                continue
            if next_page <= page:
                break
            page = next_page

        return all_discussions

    @staticmethod
    def _determine_next_page(response: object, current_page: int) -> int | None:
        """レスポンスに含まれるページ情報から次ページを判定する."""

        def _parse_page(value: object) -> int | None:
            if isinstance(value, int):
                return value if value > 0 else None
            if isinstance(value, str) and value.isdigit():
                page_value = int(value)
                return page_value if page_value > 0 else None
            return None

        if isinstance(response, dict):
            pagination = response.get("pagination")
            if isinstance(pagination, dict):
                next_page = _parse_page(pagination.get("next_page"))
                if next_page is not None:
                    return next_page
                has_next = pagination.get("has_next_page")
                if isinstance(has_next, bool):
                    return current_page + 1 if has_next else None

            next_page = _parse_page(response.get("next_page"))
            if next_page is not None:
                return next_page

            has_next_page = response.get("has_next_page")
            if isinstance(has_next_page, bool):
                return current_page + 1 if has_next_page else None

            total_pages = _parse_page(response.get("total_pages"))
            if total_pages is not None and current_page < total_pages:
                return current_page + 1

        return None


class TaskGitLabMergeRequest(Task):
    def __init__(
        self,
        mr: dict[str, Any],
        mcp_client: MCPToolClient,
        gitlab_client: GitlabClient,
        config: dict[str, Any],
    ) -> None:
        super().__init__()
        self.mr = mr
        self.project_id = mr.get("project_id")
        self.merge_request_iid = mr.get("iid")
        self.mcp_client = mcp_client
        self.gitlab_client = gitlab_client
        self.config = config
        self.labels = list(mr.get("labels", []))

    def _refresh_mr(self) -> None:
        """最新のMR情報を取得してself.mrを更新する."""
        args = {"project_id": f"{self.project_id}", "merge_request_iid": self.merge_request_iid}
        self.mr = self.mcp_client.call_tool("get_merge_request", args)
        self.labels = list(self.mr.get("labels", []))

    def prepare(self) -> None:
        # 最新のMR情報を取得
        self._refresh_mr()
        # ラベル付け変更: bot_label → processing_label
        if self.config["gitlab"]["bot_label"] in self.labels:
            self.labels.remove(self.config["gitlab"]["bot_label"])
        if self.config["gitlab"]["processing_label"] not in self.labels:
            self.labels.append(self.config["gitlab"]["processing_label"])
        # GitLabのAPIを使ってMRのラベルを更新
        self.gitlab_client.update_merge_request_labels(
            project_id=self.project_id,
            merge_request_iid=self.merge_request_iid,
            labels=self.labels,
        )
        self.mr["labels"] = self.labels

    def get_prompt(self) -> str:
        """GitLabからコメント情報を取得してプロンプトを生成する."""
        # 最新のMR情報を取得
        self._refresh_mr()
        comments = self._fetch_merge_request_notes()
        comments = [note.get("body", "") for note in comments]
        return (
            f"MERGE_REQUEST: {{'title': '{self.mr.get('title', '')}', "
            f"'description': '{self.mr.get('description', '')}', "
            f"'iid': '{self.mr.get('iid', '')}', "
            f"'source_branch': '{self.mr.get('source_branch', '')}', "
            f"'project_id': '{self.mr.get('project_id', '')}'}}\n"
            f"COMMENTS: {comments}"
        )

    def comment(self, text: str, *, mention: bool = False) -> dict[str, Any] | None:
        if mention:
            owner = self.mr.get("author", {}).get("username")
            if owner:
                text = f"@{owner} {text}"
        # GitLabのAPIを使ってMRの記録を追加
        return self.gitlab_client.add_merge_request_note(
            project_id=self.project_id, merge_request_iid=self.merge_request_iid, body=text,
        )

    def update_comment(self, comment_id: int | str, text: str) -> None:
        """Update an existing merge request comment."""
        self.gitlab_client.update_merge_request_note(
            self.project_id,
            self.merge_request_iid,
            comment_id,
            text,
        )

    def finish(self) -> None:
        # 最新のMR情報を取得
        self._refresh_mr()
        # ラベル付け変更: processing_label → done_label
        if self.config["gitlab"]["processing_label"] in self.labels:
            self.labels.remove(self.config["gitlab"]["processing_label"])
        if self.config["gitlab"]["done_label"] not in self.labels:
            self.labels.append(self.config["gitlab"]["done_label"])
        # GitLabのAPIを使ってMRのラベルを更新
        self.gitlab_client.update_merge_request_labels(
            project_id=self.project_id,
            merge_request_iid=self.merge_request_iid,
            labels=self.labels,
        )
        self.mr["labels"] = self.labels

    def get_task_key(self) -> GitLabMergeRequestTaskKey:
        return GitLabMergeRequestTaskKey(self.project_id, self.merge_request_iid)

    def check(self) -> bool:
        # 最新のMR情報を取得
        self._refresh_mr()
        return self.config["gitlab"]["processing_label"] in self.labels

    def add_label(self, label: str) -> None:
        """MRにラベルを追加する."""
        if label not in self.labels:
            self.labels.append(label)
            self.gitlab_client.update_merge_request_labels(
                project_id=self.project_id,
                merge_request_iid=self.merge_request_iid,
                labels=self.labels,
            )
            self.mr["labels"] = self.labels

    def remove_label(self, label: str) -> None:
        """MRからラベルを削除する."""
        if label in self.labels:
            self.labels.remove(label)
            self.gitlab_client.update_merge_request_labels(
                project_id=self.project_id,
                merge_request_iid=self.merge_request_iid,
                labels=self.labels,
            )
            self.mr["labels"] = self.labels

    def get_user(self) -> str | None:
        """Merge Requestの作成者のユーザー名を取得する."""
        return self.mr.get("author", {}).get("username")

    @property
    def title(self) -> str:
        """Merge Requestのタイトルを取得する."""
        return self.mr.get("title", "")

    @property
    def body(self) -> str:
        """Merge Requestの本文を取得する."""
        return self.mr.get("description", "")

    def get_assignees(self) -> list[str]:
        """Merge Requestにアサインされているユーザー名のリストを取得する."""
        # GitLabでは assignees (複数) と assignee (単一) の両方がある
        assignees = self.mr.get("assignees", [])
        if assignees:
            return [a.get("username", "") for a in assignees if a.get("username")]
        
        # assignees が空の場合は assignee を確認
        assignee = self.mr.get("assignee")
        if assignee and assignee.get("username"):
            return [assignee.get("username")]
        
        return []

    def refresh_assignees(self) -> list[str]:
        """APIからアサイン情報を再取得して返す."""
        # Fetch latest MR data from GitLab API
        updated_mr = self.gitlab_client.get_merge_request(
            project_id=self.project_id,
            mr_iid=self.merge_request_iid,
        )
        
        # Update internal state
        self.mr["assignees"] = updated_mr.get("assignees", [])
        self.mr["assignee"] = updated_mr.get("assignee")
        
        return self.get_assignees()

    def get_comments(self) -> list[dict[str, Any]]:
        """Merge Requestの全コメントを取得する.

        Returns:
            コメント情報のリスト
        """
        raw_notes = self._fetch_merge_request_notes()
        
        # 標準形式に変換
        comments = []
        for note in raw_notes:
            comments.append({
                "id": note.get("id"),
                "author": note.get("author", {}).get("username", ""),
                "body": note.get("body", ""),
                "created_at": note.get("created_at", ""),
                "updated_at": note.get("updated_at"),
            })
        
        return comments

    def _fetch_merge_request_notes(self) -> list[dict[str, Any]]:
        """MRに紐づくノートを設定に応じて全件取得する."""
        per_page: int = 100
        max_pages: int = 200

        gitlab_config = self.config.get("gitlab", {})
        configured_per_page = gitlab_config.get("mr_notes_per_page")
        if isinstance(configured_per_page, int) and configured_per_page > 0:
            per_page = configured_per_page

        configured_max_pages = gitlab_config.get("mr_notes_max_pages")
        if isinstance(configured_max_pages, int) and configured_max_pages > 0:
            max_pages = configured_max_pages

        return self.gitlab_client.list_merge_request_notes(
            project_id=self.project_id,
            merge_request_iid=self.merge_request_iid,
            per_page=per_page,
            max_pages=max_pages,
        )


class TaskGetterFromGitLab(TaskGetter):
    def __init__(self, config: dict[str, Any], mcp_clients: dict[str, MCPToolClient]) -> None:
        self.config = config
        self.mcp_client = mcp_clients["gitlab"]
        self.gitlab_client = GitlabClient()

    def get_task_list(self) -> list[Task]:
        tasks = []

        query = self.config["gitlab"].get("query", "")
        assignee = self.config["gitlab"].get("assignee")
        if not assignee:
            assignee = self.config["gitlab"].get("owner", "")
        issues = self.gitlab_client.search_issues(query)
        issues = [
            issue
            for issue in issues
            if self.config["gitlab"]["bot_label"] in issue.get("labels")
            and (issue.get("assignee") or {}).get("username", "") == assignee
        ]
        tasks.extend([
            TaskGitLabIssue(issue, self.mcp_client, self.gitlab_client, self.config)
            for issue in issues
        ])

        merge_requests = self.gitlab_client.search_merge_requests(query)
        merge_requests = [
            mr
            for mr in merge_requests
            if self.config["gitlab"]["bot_label"] in mr.get("labels")
            and mr.get("assignee", {}).get("username", "") == assignee
        ]
        tasks.extend([
            TaskGitLabMergeRequest(mr, self.mcp_client, self.gitlab_client, self.config)
            for mr in merge_requests
        ])

        return tasks

    def from_task_key(self, task_key_dict: dict[str, Any]) -> Task | None:
        ttype = task_key_dict.get("type")
        if ttype == "gitlab_issue":
            task_key = GitLabIssueTaskKey.from_dict(task_key_dict)
            issue = self.mcp_client.call_tool(
                "get_issue",
                {"project_id": str(task_key.project_id), "issue_iid": task_key.issue_iid},
            )
            return TaskGitLabIssue(issue, self.mcp_client, self.gitlab_client, self.config)
        if ttype == "gitlab_merge_request":
            task_key = GitLabMergeRequestTaskKey.from_dict(task_key_dict)
            mr = self.gitlab_client.get_merge_request(
                project_id=task_key.project_id, mr_iid=task_key.mr_iid,
            )
            return TaskGitLabMergeRequest(mr, self.mcp_client, self.gitlab_client, self.config)
        return None
