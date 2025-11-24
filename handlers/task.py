"""タスクの抽象基底クラス.

このモジュールは、GitHubやGitLabのIssue・Pull Request・Merge Request等の
様々なタスクを統一的に扱うための抽象基底クラスを定義しています。
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from handlers.task_key import TaskKey


class Task(ABC):
    """タスクの抽象基底クラス.

    GitHubのIssue・Pull RequestやGitLabのIssue・Merge Request等の
    様々なタスクを統一的に処理するためのインターフェースを定義します。
    """

    def __init__(self) -> None:
        """Initialize task with UUID placeholder."""
        self.uuid: str | None = None
        self.user: str | None = None

    @abstractmethod
    def prepare(self) -> None:
        """タスクの準備処理を実行する.

        例:processing用のラベルの付与など、タスク処理開始前に
        必要な準備作業を行います。
        """

    @abstractmethod
    def get_prompt(self) -> str:
        """LLMに渡すプロンプトを生成する.

        タスクの内容に基づいて、LLMに送信するための適切な
        プロンプト文字列を生成します。

        Returns:
            LLMに送信するプロンプト文字列

        """

    @abstractmethod
    def comment(self, text: str, *, mention: bool = False) -> None:
        """タスクにコメントを追加する.

        Args:
            text: 追加するコメントのテキスト
            mention: Trueの場合、タスクの作成者にメンションを送信

        """

    @abstractmethod
    def finish(self) -> None:
        """タスクの完了処理を実行する.

        例:processing用ラベルの削除やdoneラベルの付与など、
        タスク処理完了後に必要な処理を行います。
        """

    @abstractmethod
    def check(self) -> bool:
        """タスクの状態を確認する.

        タスクが処理可能な状態かどうかを確認します。
        例:processing用のラベルが付与されているかなど。

        Returns:
            タスクが処理可能な場合True、そうでなければFalse

        """

    @abstractmethod
    def get_task_key(self) -> "TaskKey":
        """タスクの一意なキーを取得する.

        タスクを識別するための一意なキーオブジェクトを返します。
        このキーはタスクの永続化や復元に使用されます。

        Returns:
            タスクの一意なキーオブジェクト

        """

    @abstractmethod
    def get_user(self) -> str | None:
        """タスクの作成者のユーザー名を取得する.

        Returns:
            ユーザー名、取得できない場合はNone

        """

    @property
    @abstractmethod
    def title(self) -> str:
        """タスクのタイトルを取得する.

        Returns:
            タスクのタイトル

        """

    @property
    @abstractmethod
    def body(self) -> str:
        """タスクの本文を取得する.

        Returns:
            タスクの本文

        """
