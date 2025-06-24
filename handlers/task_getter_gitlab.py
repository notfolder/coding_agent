import json
from .task_getter import TaskGetter

class TaskGitLabIssue:
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
        self.mcp_client.call_tool('gitlab/update_issue', args)

    def get_prompt(self):
        # issue本体取得
        args = {
            'project_id': f"{self.project_id}",
            'issue_iid': self.issue_iid
        }
        issue_detail = self.mcp_client.call_tool('gitlab/get_issue', args)
        # コメント取得（GitLabはノートとして管理）
        comments = []
        note_args = {
            'project_id': f"{self.project_id}",
            'issue_iid': self.issue_iid
        }
        comments = self.mcp_client.call_tool('gitlab/list_issue_discussions', note_args)
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
        self.mcp_client.call_tool('gitlab/create_note', args)

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
        self.mcp_client.call_tool('gitlab/update_issue', args)

class TaskGetterFromGitLab(TaskGetter):
    def __init__(self, config, mcp_clients):
        self.config = config
        self.mcp_client = mcp_clients['gitlab']

    def get_task_list(self):
        # まず全プロジェクトを取得
        projects_result = self.mcp_client.call_tool('gitlab/search_repositories', {
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
                'per_page': 20
            }
            result = self.mcp_client.call_tool('gitlab/list_issues', args)
            issues = result
            for issue in issues:
                all_issues.append(TaskGitLabIssue(issue, self.mcp_client, self.config))
        return all_issues
