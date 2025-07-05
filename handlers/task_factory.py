from abc import ABC, abstractmethod
from .task_key import TaskKey, GitHubIssueTaskKey, GitHubPullRequestTaskKey, GitLabIssueTaskKey, GitLabMergeRequestTaskKey

class TaskFactory(ABC):
    @abstractmethod
    def create_task(self, task_key: TaskKey):
        pass

class GitHubTaskFactory(TaskFactory):
    def __init__(self, mcp_client, github_client, config):
        self.mcp_client = mcp_client
        self.github_client = github_client
        self.config = config
    def create_task(self, task_key: TaskKey):
        if isinstance(task_key, GitHubIssueTaskKey):
            issue = self.mcp_client.call_tool('get_issue', {
                'owner': task_key.owner,
                'repo': task_key.repo,
                'issue_number': task_key.number
            })
            from .task_getter_github import TaskGitHubIssue
            return TaskGitHubIssue(issue, self.mcp_client, self.config)
        elif isinstance(task_key, GitHubPullRequestTaskKey):
            pr = self.github_client.get_pull_request(
                owner=task_key.owner,
                repo=task_key.repo,
                pull_number=task_key.number
            )
            from .task_getter_github import TaskGitHubPullRequest
            return TaskGitHubPullRequest(pr, self.mcp_client, self.github_client, self.config)
        else:
            raise ValueError('Unknown task key type for GitHub')

class GitLabTaskFactory(TaskFactory):
    def __init__(self, mcp_client, gitlab_client, config):
        self.mcp_client = mcp_client
        self.gitlab_client = gitlab_client
        self.config = config
    def create_task(self, task_key: TaskKey):
        if isinstance(task_key, GitLabIssueTaskKey):
            issue = self.mcp_client.call_tool('get_issue', {
                'project_id': task_key.project_id,
                'issue_iid': task_key.issue_iid
            })
            from .task_getter_gitlab import TaskGitLabIssue
            return TaskGitLabIssue(issue, self.mcp_client, self.config)
        elif isinstance(task_key, GitLabMergeRequestTaskKey):
            mr = self.gitlab_client.get_merge_request(
                project_id=task_key.project_id,
                mr_iid=task_key.mr_iid
            )
            from .task_getter_gitlab import TaskGitLabMergeRequest
            return TaskGitLabMergeRequest(mr, self.mcp_client, self.gitlab_client, self.config)
        else:
            raise ValueError('Unknown task key type for GitLab')
