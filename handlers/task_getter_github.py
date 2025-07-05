import json

from clients.github_client import GithubClient
from .task_getter import TaskGetter
from .task import Task
from .task_key import GitHubIssueTaskKey, GitHubPullRequestTaskKey

class TaskGitHubIssue(Task):
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
        self.mcp_client.call_tool('update_issue', args)

    def get_prompt(self):
        # issue内容・コメント取得
        args = {
            'owner': self.config['github']['owner'],
            'repo': self.issue['repo'],
            'issue_number': self.issue['number']
        }
        # issue = self.mcp_client.call_tool('get_issue', args)
        comments = [comment.get('body', '') for comment in self.mcp_client.call_tool('get_issue_comments', args)]
        return (
            f"ISSUE: {{'title': '{self.issue.get('title', '')}', "
            f"'body': '{self.issue.get('body', '')}', "
            f"'owner': '{self.issue.get('owner', '')}', "
            f"'repo': '{self.issue.get('repo', '')}'}}\n"
            f"COMMENTS: {comments}"
        )

    def comment(self, text, mention=False):
        if mention:
            owner = self.issue.get('owner')
            if owner:
                text = f"@{owner} {text}"
        args = {
            'owner': self.config['github']['owner'],
            'repo': self.issue['repo'],
            'issue_number': self.issue['number'],
            'body': text
        }
        self.mcp_client.call_tool('add_issue_comment', args)

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
        self.mcp_client.call_tool('update_issue', args)

    def get_task_key(self):
        return GitHubIssueTaskKey(self.issue['owner'], self.issue['repo'], self.issue['number'])

    def check(self):
        return self.config['github']['processing_label'] in self.labels

class TaskGitHubPullRequest(Task):
    def __init__(self, pr, mcp_client, github_client, config):
        self.pr = pr
        self.pr['repo'] = pr['base']['repo']['name']
        self.pr['owner'] = pr['base']['repo']['owner']['login']
        self.mcp_client = mcp_client
        self.github_client = github_client
        self.config = config
        self.labels = pr.get('labels', [])

    def prepare(self):
        # ラベル付け変更
        self.labels.append(self.config['github']['processing_label'])
        self.labels = list(set(self.labels))
        if self.config['github']['bot_label'] in self.labels:
            self.labels.remove(self.config['github']['bot_label'])
        self.pr['labels'] = self.labels
        self.github_client.update_pull_request_labels(self.pr['owner'], self.pr['repo'], self.pr['number'], self.labels)

    def get_prompt(self):
        comments = self.github_client.get_pull_request_comments(
            owner=self.pr['owner'],
            repo=self.pr['repo'],
            pull_number=self.pr['number']
        )
        pr_info = {
            'pull_request': {
                'title': self.pr.get('title', ''),
                'body': self.pr.get('body', ''),
                'owner': self.pr.get('owner', ''),
                'repo': self.pr.get('repo', ''),
                'pullNumber': self.pr.get('number', ''),
                'branch': self.pr.get('head', {}).get('ref', '')
            },
            'comments': comments
        }
        return f"PULL_REQUEST: {json.dumps(pr_info, ensure_ascii=False)}\n"

    def comment(self, text, mention=False):
        if mention:
            owner = self.pr.get('owner')
            if owner:
                text = f"@{owner} {text}"
        self.github_client.add_comment_to_pull_request(
            owner=self.pr['owner'],
            repo=self.pr['repo'],
            pull_number=self.pr['number'],
            body=text
        )

    def finish(self):
        label = self.config['github']['processing_label']
        if label in self.labels:
            self.labels.remove(label)
        self.labels.append(self.config['github']['done_label'])
        self.pr['labels'] = self.labels
        args = {
            'owner': self.config['github']['owner'],
            'repo': self.pr['repo'],
            'pull_number': self.pr['number'],
            'labels': self.labels
        }
        self.github_client.update_pull_request_labels(self.pr['owner'], self.pr['repo'], self.pr['number'], self.labels)

    def get_task_key(self):
        return GitHubPullRequestTaskKey(self.pr['owner'], self.pr['repo'], self.pr['number'])

    def check(self):
        return self.config['github']['processing_label'] in self.labels

class TaskGetterFromGitHub(TaskGetter):
    def __init__(self, config, mcp_clients):
        self.config = config
        self.mcp_client = mcp_clients['github']
        self.github_client = GithubClient()

    def get_task_list(self):
        # MCPサーバーでissue検索
        args = {
            'q': f'label:"{self.config["github"]["bot_label"]}" {self.config["github"].get("query", "")}',
            'perPage': 20
        }
        result = self.mcp_client.call_tool('search_issues', args)
        issues = result.get('items', [])
        tasks = [TaskGitHubIssue(issue, self.mcp_client, self.config) for issue in issues]

        # リポジトリループ
        repositories = self.mcp_client.call_tool('search_repositories', {
            'query': "user:" + self.config['github']['owner'],
            'per_page': 200
        })
        repositories = repositories.get('items', [])
        # Pull Requestの取得
        for repo in repositories:
            prs = self.github_client.list_pull_requests_with_label(
                owner= repo['owner']['login'],
                repo= repo['name'],
                label=self.config['github']['bot_label']
            )
            for pr in prs:
                tasks.append(TaskGitHubPullRequest(pr, self.mcp_client, self.github_client, self.config))
        return tasks

    def from_task_key(self, task_key_dict):
        ttype = task_key_dict.get('type')
        if ttype == 'github_issue':
            from .task_key import GitHubIssueTaskKey
            task_key = GitHubIssueTaskKey.from_dict(task_key_dict)
            issue = self.mcp_client.call_tool('get_issue', {
                'owner': task_key.owner,
                'repo': task_key.repo,
                'issue_number': task_key.number
            })
            return TaskGitHubIssue(issue, self.mcp_client, self.config)
        elif ttype == 'github_pull_request':
            from .task_key import GitHubPullRequestTaskKey
            task_key = GitHubPullRequestTaskKey.from_dict(task_key_dict)
            pr = self.github_client.get_pull_request(
                owner=task_key.owner,
                repo=task_key.repo,
                pull_number=task_key.number
            )
            return TaskGitHubPullRequest(pr, self.mcp_client, self.github_client, self.config)
        else:
            return None
