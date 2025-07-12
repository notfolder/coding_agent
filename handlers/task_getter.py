from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, NoReturn

if TYPE_CHECKING:
    from .task_getter_github import TaskGetterFromGitHub
    from .task_getter_gitlab import TaskGetterFromGitLab


class TaskGetter(ABC):
    @abstractmethod
    def get_task_list(self) -> list[dict[str, Any]]:
        pass

    @classmethod
    def factory(
        cls,
        config: dict[str, Any],
        mcp_clients: dict[str, Any],
        task_source: str,
    ) -> TaskGetterFromGitHub | TaskGetterFromGitLab:
        # Import here to avoid circular import issues
        if task_source == "github":
            from .task_getter_github import TaskGetterFromGitHub  # noqa: PLC0415
            return TaskGetterFromGitHub(config, mcp_clients)
        if task_source == "gitlab":
            from .task_getter_gitlab import TaskGetterFromGitLab  # noqa: PLC0415
            return TaskGetterFromGitLab(config, mcp_clients)
        msg = f"Unknown task_source: {task_source}"
        raise ValueError(msg)

    @abstractmethod
    def from_task_key(self, task_key_dict: dict[str, Any]) -> NoReturn:
        """タスクキーからタスクを生成."""
        msg = "from_task_keyはサブクラスで実装してください"
        raise NotImplementedError(msg)
