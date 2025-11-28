"""タスクの抽象基底クラス.

このモジュールは、GitHubやGitLabのIssue・Pull Request・Merge Request等の
様々なタスクを統一的に扱うための抽象基底クラスを定義しています。
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

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
    def comment(self, text: str, *, mention: bool = False) -> dict[str, Any] | None:
        """タスクにコメントを追加する.

        Args:
            text: 追加するコメントのテキスト
            mention: Trueの場合、タスクの作成者にメンションを送信

        Returns:
            作成されたコメントの情報 (IDを含む辞書)、失敗時はNone

        """

    @abstractmethod
    def update_comment(self, comment_id: int | str, text: str) -> None:
        """既存のコメントを更新する.

        Args:
            comment_id: 更新するコメントのID
            text: 更新後のコメントのテキスト

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
    def add_label(self, label: str) -> None:
        """タスクにラベルを追加する.

        Args:
            label: 追加するラベル名

        """

    @abstractmethod
    def remove_label(self, label: str) -> None:
        """タスクからラベルを削除する.

        Args:
            label: 削除するラベル名

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

    @abstractmethod
    def get_assignees(self) -> list[str]:
        """タスクにアサインされているユーザー名のリストを取得する.

        タスクオブジェクト内にキャッシュされているアサイン情報を返します。
        最新情報を取得する場合は refresh_assignees() を使用してください。

        Returns:
            アサインされているユーザー名のリスト

        """

    @abstractmethod
    def refresh_assignees(self) -> list[str]:
        """アサイン情報をAPIから再取得して返す.

        GitHub/GitLab APIを呼び出して最新のアサイン情報を取得し、
        内部状態を更新してから返します。

        Returns:
            アサインされているユーザー名のリスト

        Raises:
            Exception: API呼び出しに失敗した場合

        """

    @abstractmethod
    def get_comments(self) -> list[dict[str, Any]]:
        """Issue/MRの全コメントを取得する.

        Returns:
            コメント情報のリスト。各コメントは以下の構造を持つ:
            - id: コメントの一意識別子（int または str）
            - author: コメント作成者のユーザー名（str）
            - body: コメント本文（str）
            - created_at: 作成日時（ISO 8601形式、str）
            - updated_at: 更新日時（ISO 8601形式、オプション、str | None）

        """
