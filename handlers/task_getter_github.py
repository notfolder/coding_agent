import json
from .task_getter import TaskGetter

class TaskGitHubIssue:
    def __init__(self, issue, mcp_client, config):
        self.issue = issue
        self.issue['repo'] = issue['repository_url'].split('/')[-1]
        self.issue['owner'] = issue['repository_url'].split('/')[-2]
        self.mcp_client = mcp_client
        self.config = config
        self.labels = [label.get('name', '') for label in issue.get('labels', [])]

    def prepare(self):
        # ラベル付け変更
        self.labels.append(self.config['github']['processing_label'])
        self.labels.remove(self.config['github']['bot_label']) if self.config['github']['bot_label'] in self.labels else None
        self.issue['labels'] = self.labels
        args = {
            'owner': self.config['github']['owner'],
            'repo': self.issue['repo'],
            'issue_number': self.issue['number'],
            # 'remove_labels': [self.config['github']['bot_label']],
            'labels': self.labels
        }
        self.mcp_client.call_tool('github/update_issue', args)

    def get_prompt(self):
        # issue内容・コメント取得
        args = {
            'owner': self.config['github']['owner'],
            'repo': self.issue['repo'],
            'issue_number': self.issue['number']
        }
        # issue = self.mcp_client.call_tool('github/get_issue', args)
        comments = [comment.get('body', '') for comment in self.mcp_client.call_tool('github/get_issue_comments', args)]
        return (
            f"ISSUE: {{'title': '{self.issue.get('title', '')}', "
            f"'body': '{self.issue.get('body', '')}', "
            f"'owner': '{self.issue.get('owner', '')}', "
            f"'repo': '{self.issue.get('repo', '')}'}}\n"
            f"COMMENTS: {comments}"
        )

    def comment(self, text):
        args = {
            'owner': self.config['github']['owner'],
            'repo': self.issue['repo'],
            'issue_number': self.issue['number'],
            'body': text
        }
        self.mcp_client.call_tool('github/add_issue_comment', args)

    def finish(self):
        # ラベル付け変更
        label = self.config['github']['processing_label']
        self.labels.remove(label) if label in self.labels else None
        self.labels.append(self.config['github']['done_label'])
        self.issue['labels'] = self.labels
        args = {
            'owner': self.config['github']['owner'],
            'repo': self.issue['repo'],
            'issue_number': self.issue['number'],
            'labels': self.labels
        }
        self.mcp_client.call_tool('github/update_issue', args)

class TaskGetterFromGitHub(TaskGetter):
    def __init__(self, config, mcp_clients):
        self.config = config
        self.mcp_client = mcp_clients['github']

    def get_task_list(self):
        # MCPサーバーでissue検索
        args = {
            'q': f'label:"{self.config["github"]["bot_label"]}" {self.config["github"].get("query", "")}',
            'perPage': 20
        }
        result = self.mcp_client.call_tool('github/search_issues', args)
        # result = self.mcp_client.call_tool('github/get_me', {})
        issues = result.get('items', [])
        return [TaskGitHubIssue(issue, self.mcp_client, self.config) for issue in issues]
