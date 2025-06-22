from abc import ABC, abstractmethod

class TaskGetter(ABC):
    @abstractmethod
    def get_task_list(self):
        pass

    @staticmethod
    def factory(config, mcp_clients, task_source):
        # 設定に応じて適切なTaskGetterを返す
        if task_source == 'github':
            from .task_getter_github import TaskGetterFromGitHub
            mcp_clients.pop('gitlab', None)  # GitLabクライアントを削除
            return TaskGetterFromGitHub(config, mcp_clients)
        elif task_source == 'gitlab':
            from .task_getter_gitlab import TaskGetterFromGitLab
            mcp_clients.pop('github', None)  # GitHubクライアントを削除
            return TaskGetterFromGitLab(config, mcp_clients)
        raise NotImplementedError('No TaskGetter implemented for config')
