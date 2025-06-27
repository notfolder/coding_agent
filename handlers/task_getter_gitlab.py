import json
from .task import Task
from .task_getter import TaskGetter

class TaskGitLabIssue(Task):
    def __init__(self, issue, mcp_client, config):
        self.issue = issue
        self.project_id = issue.get('project_id')
        self.issue_iid = issue.get('iid')
        self.mcp_client = mcp_client
        self.config = config

    def prepare(self):
        # ラベル付け変更: bot_label → processing_label
        labels = self.issue.get('labels', [])
        if self.config['gitlab']['bot_label'] in labels:
            labels.remove(self.config['gitlab']['bot_label'])
        if self.config['gitlab']['processing_label'] not in labels:
            labels.append(self.config['gitlab']['processing_label'])
        args = {
            'project_id': f"{self.project_id}",
            'issue_iid': self.issue_iid,
            'labels': labels
        }
        self.issue['labels'] = labels
        self.mcp_client.call_tool('update_issue', args)

    def get_prompt(self):
        # issue本体取得
        args = {
            'project_id': f"{self.project_id}",
            'issue_iid': self.issue_iid
        }
        issue_detail = self.mcp_client.call_tool('get_issue', args)
        # コメント取得（GitLabはノートとして管理）
        comments = []
        note_args = {
            'project_id': f"{self.project_id}",
            'issue_iid': self.issue_iid
        }
        comments = self.mcp_client.call_tool('list_issue_discussions', note_args)
        comments = [[note.get('body', '') for note in item.get('notes', [])] for item in comments.get('items', [])]
        return (
            f"ISSUE: {{'title': '{self.issue.get('title', '')}', "
            f"'description': '{self.issue.get('description', '')}', "
            f"'project_id': '{self.issue.get('project_id', '')}'}}\n"
            f"COMMENTS: {comments}"
        )

    def comment(self, text, mention=False):
        if mention:
            owner = self.issue.get('author', {}).get('username')
            if owner:
                text = f"@{owner} {text}"
        args = {
            'project_id': f"{self.project_id}",
            'noteable_type': 'issue',
            'noteable_iid': self.issue_iid,
            'body': text
        }
        self.mcp_client.call_tool('create_note', args)

    def finish(self):
        # ラベル付け変更: processing_label → done_label
        labels = self.issue.get('labels', [])
        if self.config['gitlab']['processing_label'] in labels:
            labels.remove(self.config['gitlab']['processing_label'])
        if self.config['gitlab']['done_label'] not in labels:
            labels.append(self.config['gitlab']['done_label'])
        args = {
            'project_id': f"{self.project_id}",
            'issue_iid': self.issue_iid,
            'labels': labels
        }
        self.issue['labels'] = labels
        self.mcp_client.call_tool('update_issue', args)

class TaskGitLabMergeRequest(Task):
    def __init__(self, mr, mcp_client, config):
        self.mr = mr
        self.project_id = mr.get('project_id')
        self.merge_request_iid = mr.get('iid')
        self.mcp_client = mcp_client
        self.config = config
        self.labels = [label for label in mr.get('labels', [])]

    def prepare(self):
        # ラベル付け変更: bot_label → processing_label
        if self.config['gitlab']['bot_label'] in self.labels:
            self.labels.remove(self.config['gitlab']['bot_label'])
        if self.config['gitlab']['processing_label'] not in self.labels:
            self.labels.append(self.config['gitlab']['processing_label'])
        args = {
            'project_id': f"{self.project_id}",
            'merge_request_iid': self.merge_request_iid,
            'labels': self.labels
        }
        self.mr['labels'] = self.labels
        self.mcp_client.call_tool('update_merge_request', args)

    def get_prompt(self):
        # MR本体取得
        args = {
            'project_id': f"{self.project_id}",
            'merge_request_iid': self.merge_request_iid
        }
        mr_detail = self.mcp_client.call_tool('get_merge_request', args)
        # コメント取得（GitLabはノートとして管理）
        note_args = {
            'project_id': f"{self.project_id}",
            'merge_request_iid': self.merge_request_iid
        }
        comments = self.mcp_client.call_tool('list_merge_request_notes', note_args)
        comments = [note.get('body', '') for note in comments.get('items', [])]
        return (
            f"MERGE_REQUEST: {{'title': '{self.mr.get('title', '')}', "
            f"'description': '{self.mr.get('description', '')}', "
            f"'project_id': '{self.mr.get('project_id', '')}'}}\n"
            f"COMMENTS: {comments}"
        )

    def comment(self, text, mention=False):
        if mention:
            owner = self.mr.get('author', {}).get('username')
            if owner:
                text = f"@{owner} {text}"
        args = {
            'project_id': f"{self.project_id}",
            'merge_request_iid': self.merge_request_iid,
            'body': text
        }
        self.mcp_client.call_tool('create_merge_request_note', args)

    def finish(self):
        # ラベル付け変更: processing_label → done_label
        if self.config['gitlab']['processing_label'] in self.labels:
            self.labels.remove(self.config['gitlab']['processing_label'])
        if self.config['gitlab']['done_label'] not in self.labels:
            self.labels.append(self.config['gitlab']['done_label'])
        args = {
            'project_id': f"{self.project_id}",
            'merge_request_iid': self.merge_request_iid,
            'labels': self.labels
        }
        self.mr['labels'] = self.labels
        self.mcp_client.call_tool('update_merge_request', args)

class TaskGetterFromGitLab(TaskGetter):
    def __init__(self, config, mcp_clients):
        self.config = config
        self.mcp_client = mcp_clients['gitlab']

    def get_task_list(self):
        # まず全プロジェクトを取得
        projects_result = self.mcp_client.call_tool('search_repositories', {
            'search': '',  # 空文字で全プロジェクト取得
            'per_page': 100
        })
        projects = projects_result.get('items', [])
        all_issues = []
        for project in projects:
            project_id = project.get('id')
            if not project_id:
                continue
            args = {
                'project_id': f"{project_id}",
                'state': 'opened',
                'labels': [self.config['gitlab']['bot_label']],
                'per_page': 200
            }
            result = self.mcp_client.call_tool('list_issues', args)
            issues = result
            for issue in issues:
                all_issues.append(TaskGitLabIssue(issue, self.mcp_client, self.config))
            
            # # マージリクエストの取得
            # MCPサーバーの機能不足でGitLabのマージリクエスト対応は断念
            # merge_request_args = {
            #     'project_id': f"{project_id}",
            #     'state': 'opened',
            #     'labels': [self.config['gitlab']['bot_label']],
            #     'per_page': 200
            # }
            # merge_requests = self.mcp_client.call_tool('list_merge_requests', merge_request_args)
            # for mr in merge_requests:
            #     all_issues.append(TaskGitLabMergeRequest(mr, self.mcp_client, self.config))
        return all_issues
