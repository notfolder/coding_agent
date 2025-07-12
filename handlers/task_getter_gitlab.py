
from clients.gitlab_client import GitlabClient

from .task import Task
from .task_getter import TaskGetter
from .task_key import GitLabIssueTaskKey, GitLabMergeRequestTaskKey


class TaskGitLabIssue(Task):
    def __init__(self, issue, mcp_client, gitlab_client, config) -> None:
        self.issue = issue
        self.project_id = issue.get("project_id")
        self.issue_iid = issue.get("iid")
        self.mcp_client = mcp_client
        self.gitlab_client = gitlab_client
        self.config = config

    def prepare(self) -> None:
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
        # issue本体取得
        args = {"project_id": f"{self.project_id}", "issue_iid": self.issue_iid}
        self.mcp_client.call_tool("get_issue", args)
        # コメント取得(GitLabはノートとして管理)
        comments = []
        note_args = {"project_id": f"{self.project_id}", "issue_iid": self.issue_iid}
        comments = self.mcp_client.call_tool("list_issue_discussions", note_args)
        comments = [
            [note.get("body", "") for note in item.get("notes", [])]
            for item in comments.get("items", [])
        ]
        return (
            f"ISSUE: {{'title': '{self.issue.get('title', '')}', "
            f"'description': '{self.issue.get('description', '')}', "
            f"'project_id': '{self.issue.get('project_id', '')}'\n"
            f"'issue_iid': '{self.issue.get('iid', '')}'}}\n"
            f"COMMENTS: {comments}"
        )

    def comment(self, text, mention=False) -> None:
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
        self.mcp_client.call_tool("create_note", args)

    def finish(self) -> None:
        # ラベル付け変更: processing_label → done_label
        labels = self.issue.get("labels", [])
        if self.config["gitlab"]["processing_label"] in labels:
            labels.remove(self.config["gitlab"]["processing_label"])
        if self.config["gitlab"]["done_label"] not in labels:
            labels.append(self.config["gitlab"]["done_label"])
        args = {"project_id": f"{self.project_id}", "issue_iid": self.issue_iid, "labels": labels}
        self.issue["labels"] = labels
        self.mcp_client.call_tool("update_issue", args)

    def get_task_key(self):
        return GitLabIssueTaskKey(self.project_id, self.issue_iid)

    def check(self):
        return self.config["gitlab"]["processing_label"] in self.issue.get("labels", [])


class TaskGitLabMergeRequest(Task):
    def __init__(self, mr, mcp_client, gitlab_client, config) -> None:
        self.mr = mr
        self.project_id = mr.get("project_id")
        self.merge_request_iid = mr.get("iid")
        self.mcp_client = mcp_client
        self.gitlab_client = gitlab_client
        self.config = config
        self.labels = list(mr.get("labels", []))

    def prepare(self) -> None:
        # ラベル付け変更: bot_label → processing_label
        if self.config["gitlab"]["bot_label"] in self.labels:
            self.labels.remove(self.config["gitlab"]["bot_label"])
        if self.config["gitlab"]["processing_label"] not in self.labels:
            self.labels.append(self.config["gitlab"]["processing_label"])
        # GitLabのAPIを使ってMRのラベルを更新
        self.gitlab_client.update_merge_request_labels(
            project_id=self.project_id, merge_request_iid=self.merge_request_iid, labels=self.labels,
        )
        self.mr["labels"] = self.labels

    def get_prompt(self) -> str:
        # コメント取得(GitLabはノートとして管理)
        comments = self.gitlab_client.list_merge_request_notes(
            project_id=self.project_id, merge_request_iid=self.merge_request_iid,
        )
        comments = [note.get("body", "") for note in comments]
        return (
            f"MERGE_REQUEST: {{'title': '{self.mr.get('title', '')}', "
            f"'description': '{self.mr.get('description', '')}', "
            f"'iid': '{self.mr.get('iid', '')}', "
            f"'source_branch': '{self.mr.get('source_branch', '')}', "
            f"'project_id': '{self.mr.get('project_id', '')}'}}\n"
            f"COMMENTS: {comments}"
        )

    def comment(self, text, mention=False) -> None:
        if mention:
            owner = self.mr.get("author", {}).get("username")
            if owner:
                text = f"@{owner} {text}"
        # GitLabのAPIを使ってMRのノートを追加
        self.gitlab_client.add_merge_request_note(
            project_id=self.project_id, merge_request_iid=self.merge_request_iid, body=text,
        )

    def finish(self) -> None:
        # ラベル付け変更: processing_label → done_label
        if self.config["gitlab"]["processing_label"] in self.labels:
            self.labels.remove(self.config["gitlab"]["processing_label"])
        if self.config["gitlab"]["done_label"] not in self.labels:
            self.labels.append(self.config["gitlab"]["done_label"])
        # GitLabのAPIを使ってMRのラベルを更新
        self.gitlab_client.update_merge_request_labels(
            project_id=self.project_id, merge_request_iid=self.merge_request_iid, labels=self.labels,
        )
        self.mr["labels"] = self.labels

    def get_task_key(self):
        return GitLabMergeRequestTaskKey(self.project_id, self.merge_request_iid)

    def check(self):
        return self.config["gitlab"]["processing_label"] in self.labels


class TaskGetterFromGitLab(TaskGetter):
    def __init__(self, config, mcp_clients) -> None:
        self.config = config
        self.mcp_client = mcp_clients["gitlab"]
        self.gitlab_client = GitlabClient()

    def get_task_list(self):
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
            and issue.get("assignee", {}).get("username", "") == assignee
        ]
        for issue in issues:
            tasks.append(TaskGitLabIssue(issue, self.mcp_client, self.gitlab_client, self.config))

        merge_requests = self.gitlab_client.search_merge_requests(query)
        merge_requests = [
            mr
            for mr in merge_requests
            if self.config["gitlab"]["bot_label"] in mr.get("labels")
            and mr.get("assignee", {}).get("username", "") == assignee
        ]
        for mr in merge_requests:
            tasks.append(
                TaskGitLabMergeRequest(mr, self.mcp_client, self.gitlab_client, self.config),
            )

        return tasks

    def from_task_key(self, task_key_dict):
        ttype = task_key_dict.get("type")
        if ttype == "gitlab_issue":
            from .task_key import GitLabIssueTaskKey

            task_key = GitLabIssueTaskKey.from_dict(task_key_dict)
            issue = self.mcp_client.call_tool(
                "get_issue",
                {"project_id": str(task_key.project_id), "issue_iid": task_key.issue_iid},
            )
            return TaskGitLabIssue(issue, self.mcp_client, self.gitlab_client, self.config)
        if ttype == "gitlab_merge_request":
            from .task_key import GitLabMergeRequestTaskKey

            task_key = GitLabMergeRequestTaskKey.from_dict(task_key_dict)
            mr = self.gitlab_client.get_merge_request(
                project_id=task_key.project_id, mr_iid=task_key.mr_iid,
            )
            return TaskGitLabMergeRequest(mr, self.mcp_client, self.gitlab_client, self.config)
        return None
