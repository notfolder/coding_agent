from abc import ABC, abstractmethod
from typing import NoReturn


class TaskGetter(ABC):
    @abstractmethod
    def get_task_list(self):
        pass

    @classmethod
    def factory(cls, config, mcp_clients, task_source):
        # 設定に応じて適切なTaskGetterを返す
        if task_source == "github":
            from .task_getter_github import TaskGetterFromGitHub

            return TaskGetterFromGitHub(config, mcp_clients)
        if task_source == "gitlab":
            from .task_getter_gitlab import TaskGetterFromGitLab

            return TaskGetterFromGitLab(config, mcp_clients)
        msg = f"Unknown task_source: {task_source}"
        raise ValueError(msg)

    @abstractmethod
    def from_task_key(self, task_key_dict) -> NoReturn:
        """タスクキーからタスクを生成."""
        msg = "from_task_keyはサブクラスで実装してください"
        raise NotImplementedError(msg)
