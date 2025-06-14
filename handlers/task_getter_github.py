from .task_getter import TaskGetter

class TaskGitHubIssue:
    def __init__(self, issue, mcp_client, config):
        self.issue = issue
        self.mcp_client = mcp_client
        self.config = config

    def prepare(self):
        # ラベル付け変更
        args = {
            'owner': self.config['github']['owner'],
            'repo': self.issue['repository'],
            'issue_number': self.issue['number'],
            'remove_labels': [self.config['github']['bot_label']],
            'add_labels': [self.config['github']['bot_label'] + ' processing']
        }
        self.mcp_client.call_tool('github/update_issue', args)

    def get_prompt(self):
        # issue内容・コメント取得
        args = {
            'owner': self.config['github']['owner'],
            'repo': self.issue['repository'],
            'issue_number': self.issue['number']
        }
        issue = self.mcp_client.call_tool('github/get_issue', args)
        comments = self.mcp_client.call_tool('github/get_issue_comments', args)
        return f"ISSUE: {issue}\nCOMMENTS: {comments}"

    def comment(self, text):
        args = {
            'owner': self.config['github']['owner'],
            'repo': self.issue['repository'],
            'issue_number': self.issue['number'],
            'body': text
        }
        self.mcp_client.call_tool('github/add_issue_comment', args)

    def finish(self):
        args = {
            'owner': self.config['github']['owner'],
            'repo': self.issue['repository'],
            'issue_number': self.issue['number'],
            'remove_labels': [self.config['github']['bot_label'] + ' processing']
        }
        self.mcp_client.call_tool('github/update_issue', args)

class TaskGetterFromGitHub(TaskGetter):
    def __init__(self, config, mcp_clients):
        self.config = config
        self.mcp_client = mcp_clients['github']

    def get_task_list(self):
        # MCPサーバーでissue検索
        args = {
            'query': f'label:"{self.config["github"]["bot_label"]}" {self.config["github"].get("query", "")}',
            'perPage': 20
        }
        result = self.mcp_client.call_tool('github/search_issues', args)
        issues = result.get('items', [])
        return [TaskGitHubIssue(issue, self.mcp_client, self.config) for issue in issues]
