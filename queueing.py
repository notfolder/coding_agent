"""タスクキューの実装.

このモジュールは、タスクの非同期処理を実現するための
タスクキューの抽象基底クラスと具象実装を提供します。
インメモリー実装とRabbitMQ実装の両方をサポートしています。
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from queue import Empty, Queue
from typing import Any

import pika


class TaskQueue(ABC):
    """タスクキューの抽象基底クラス.

    タスクの非同期処理を実現するためのキューインターフェースを
    定義します。具象クラスはこのインターフェースを実装します。
    """

    @abstractmethod
    def put(self, task: dict[str, Any]) -> None:
        """タスクをキューに追加する.

        Args:
            task: キューに追加するタスクの辞書

        """

    @abstractmethod
    def get(self, timeout: float | None = None) -> dict[str, Any] | None:
        """キューからタスクを取得する.

        Args:
            timeout: タイムアウト時間(秒)。Noneの場合は無期限待機

        Returns:
            取得したタスクの辞書。タイムアウトした場合はNone

        """

    @abstractmethod
    def empty(self) -> bool:
        """キューが空かどうかを確認する.

        Returns:
            キューが空の場合True、そうでなければFalse

        """


class InMemoryTaskQueue(TaskQueue):
    """インメモリータスクキューの実装.

    Pythonの標準ライブラリのQueueを使用したシンプルな
    インメモリータスクキューです。単一プロセス内での
    タスク処理に適しています。
    """

    def __init__(self) -> None:
        """インメモリータスクキューを初期化する."""
        # 内部でPythonの標準Queueを使用
        self.queue: Queue[dict[str, Any]] = Queue()

    def put(self, task: dict[str, Any]) -> None:
        """タスクをキューに追加する.

        Args:
            task: キューに追加するタスクの辞書

        """
        self.queue.put(task)

    def get(self, timeout: float | None = None) -> dict[str, Any] | None:
        """キューからタスクを取得する.

        Args:
            timeout: タイムアウト時間(秒)

        Returns:
            取得したタスクの辞書。タイムアウトした場合はNone

        """
        try:
            return self.queue.get(timeout=timeout)
        except Empty:
            # タイムアウトした場合はNoneを返す
            return None

    def empty(self) -> bool:
        """キューが空かどうかを確認する.

        Returns:
            キューが空の場合True、そうでなければFalse

        """
        return self.queue.empty()


class RabbitMQTaskQueue(TaskQueue):
    """RabbitMQタスクキューの実装.

    RabbitMQメッセージブローカーを使用したタスクキューです。
    複数プロセス・複数サーバー間でのタスク分散処理に適しています。
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """RabbitMQタスクキューを初期化する.

        Args:
            config: アプリケーション設定辞書(rabbitmq設定を含む)

        """
        mq_conf = config.get("rabbitmq", {})
        self.queue_name = mq_conf.get("queue", "coding_agent_tasks")
        self.host = mq_conf.get("host", "localhost")
        self.port = mq_conf.get("port", 5672)
        self.user = mq_conf.get("user", "guest")
        self.password = mq_conf.get("password", "guest")

        # RabbitMQ認証情報を設定
        credentials = pika.PlainCredentials(self.user, self.password)

        # RabbitMQサーバーに接続
        self.connection = pika.BlockingConnection(
            pika.ConnectionParameters(
                host=self.host, port=self.port, credentials=credentials,
            ),
        )

        # チャンネルを作成し、キューを宣言
        self.channel = self.connection.channel()
        self.channel.queue_declare(queue=self.queue_name, durable=True)

    def put(self, task: dict[str, Any]) -> None:
        """タスクをRabbitMQキューに追加する.

        Args:
            task: キューに追加するタスクの辞書

        """
        # タスクをJSONにシリアライズ
        body = json.dumps(task)

        self.channel.basic_publish(
            exchange="",
            routing_key=self.queue_name,
            body=body,
            properties=pika.BasicProperties(delivery_mode=2),  # メッセージを永続化
        )

    def get(self, _timeout: float | None = None) -> dict[str, Any] | None:
        """RabbitMQキューからタスクを取得する.

        Args:
            _timeout: タイムアウト時間(秒)。現在の実装では使用されません

        Returns:
            取得したタスクの辞書。メッセージがない場合はNone

        Note:
            現在の実装ではタイムアウト機能は実装されていません。
            必要に応じて将来のバージョンで実装予定です。

        """
        method_frame, header_frame, body = self.channel.basic_get(
            queue=self.queue_name, auto_ack=True,
        )

        if method_frame:
            # メッセージが存在する場合はJSONをデシリアライズして返す
            return json.loads(body)

        # メッセージがない場合はNoneを返す
        return None

    def empty(self) -> bool:
        """RabbitMQキューが空かどうかを確認する.

        Returns:
            キューが空の場合True、そうでなければFalse

        """
        queue_info = self.channel.queue_declare(queue=self.queue_name, passive=True)

        # メッセージ数が0かどうかを返す
        return queue_info.method.message_count == 0
