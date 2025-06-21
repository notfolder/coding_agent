from abc import ABC, abstractmethod

class TaskGetter(ABC):
    @abstractmethod
    def get_task_list(self):
        pass

    @staticmethod
    def factory(config, mcp_clients):
        # 設定に応じて適切なTaskGetterを返す
        if 'github' in config:
            from .task_getter_github import TaskGetterFromGitHub
            return TaskGetterFromGitHub(config, mcp_clients)
        if 'gitlab' in config:
            from .task_getter_gitlab import TaskGetterFromGitLab
            return TaskGetterFromGitLab(config, mcp_clients)
        raise NotImplementedError('No TaskGetter implemented for config')
