import json
from .task_getter import TaskGetter
from .task import Task

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

class TaskGitHubPullRequest(Task):
    def __init__(self, pr, mcp_client, config):
        self.pr = pr
        self.pr['repo'] = pr['base']['repo']['name']
        self.pr['owner'] = pr['base']['repo']['owner']['login']
        self.mcp_client = mcp_client
        self.config = config
        self.labels = [label.get('name', '') for label in pr.get('labels', [])]

    def prepare(self):
        # ラベル付け変更
        self.labels.append(self.config['github']['processing_label'])
        self.labels = list(set(self.labels))
        if self.config['github']['bot_label'] in self.labels:
            self.labels.remove(self.config['github']['bot_label'])
        self.pr['labels'] = self.labels
        args = {
            'owner': self.config['github']['owner'],
            'repo': self.pr['repo'],
            'pullNumber': self.pr['number'],
            'labels': self.labels
        }
        self.mcp_client.call_tool('github/update_pull_request', args)

    def get_prompt(self):
        args = {
            'owner': self.config['github']['owner'],
            'repo': self.pr['repo'],
            'pullNumber': self.pr['number']
        }
        comments = [comment for comment in self.mcp_client.call_tool('github/get_pull_request_comments', args)]
        return (
            f"PULL_REQUEST: {{'title': '{self.pr.get('title', '')}', "
            f"'body': '{self.pr.get('body', '')}', "
            f"'owner': '{self.pr.get('owner', '')}', "
            f"'repo': '{self.pr.get('repo', '')}'}}\n"
            f"COMMENTS: {comments}"
        )

    def comment(self, text, mention=False):
        if mention:
            owner = self.pr.get('owner')
            if owner:
                text = f"@{owner} {text}"

        # * `github/create_pending_pull_request_review` → `{ "commitID"?: [string], "owner": string, "pullNumber": number, "repo": string }` --- Create a pending review for a pull request. Call this first before attempting to add comments to a pending review, and ultimately submitting it. A pending pull request review means a pull request review, it is pending because you create it first and submit it later, and the PR author will not see it until it is submitted.
        args = {
            'owner': self.config['github']['owner'],
            'pull_number': self.pr['number'],
            'repo': self.pr['repo'],
        }
        self.mcp_client.call_tool('github/create_pending_pull_request_review', args)

        # * `github/add_pull_request_review_comment_to_pending_review` → `{ "body": string, "line"?: [number], "owner": string, "path": string, "pullNumber": number, "repo": string, "side"?: [string], "startLine"?: [number], "startSide"?: [string], "subjectType": string }` --- Add a comment to the requester\'s latest pending pull request review, a pending review needs to already exist to call this (check with the user if not sure).
        args = {
            'owner': self.config['github']['owner'],
            'pull_number': self.pr['number'],
            'repo': self.pr['repo'],
            'body': text,
            'path': '.',
            'subjectType': 'FILE',
        }
        self.mcp_client.call_tool('github/add_pull_request_review_comment_to_pending_review', args)

        # * `github/submit_pending_pull_request_review` → `{ "body"?: [string], "event": string, "owner": string, "pullNumber": number, "repo": string }` --- Submit the requester\'s latest pending pull request review, normally this is a final step after creating a pending review, adding comments first, unless you know that the user already did the first two steps, you should check before calling this.
        args = {
            'event': 'COMMENT',
            'owner': self.config['github']['owner'],
            'pull_number': self.pr['number'],
            'repo': self.pr['repo'],
        }
        self.mcp_client.call_tool('github/submit_pending_pull_request_review', args)

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
        self.mcp_client.call_tool('github/update_pull_request', args)

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
        issues = result.get('items', [])
        tasks = [TaskGitHubIssue(issue, self.mcp_client, self.config) for issue in issues]

        # Pull Requestの取得
        # MCPサーバーの機能不足でgit hubのPull Request対応は断念
        # repo_args = {
        #     'per_page': 100,
        #     'query': f"owner:{self.config['github']['owner']}"
        # }
        # repos_result = self.mcp_client.call_tool('github/search_repositories', repo_args)
        # repos = repos_result if isinstance(repos_result, list) else repos_result.get('items', [])
        # for repo in repos:
        #     repo_name = repo.get('name')
        #     if not repo_name:
        #         continue
        #     pr_args = {
        #         'state': 'open',
        #         'per_page': 20,
        #         'owner': self.config['github']['owner'],
        #         'repo': repo_name
        #     }
        #     pr_result = self.mcp_client.call_tool('github/list_pull_requests', pr_args)
        #     prs = pr_result if isinstance(pr_result, list) else pr_result.get('items', [])
        #     for pr in prs:
        #         pr_labels = [label.get('name', '') for label in pr.get('labels', [])]
        #         if self.config['github']['bot_label'] in pr_labels:
        #             tasks.append(TaskGitHubPullRequest(pr, self.mcp_client, self.config))
        return tasks
