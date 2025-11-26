"""タスクキューの実装.

このモジュールは、タスクの非同期処理を実現するための
タスクキューの抽象基底クラスと具象実装を提供します。
インメモリー実装とRabbitMQ実装の両方をサポートしています。
"""
from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from queue import Empty, Queue
from typing import TYPE_CHECKING, Any

import pika
import pika.exceptions

if TYPE_CHECKING:
    from collections.abc import Callable


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
    def get_with_signal_check(
        self,
        timeout: float | None = None,
        signal_checker: Callable[[], bool] | None = None,
        poll_interval: float = 1.0,
    ) -> dict[str, Any] | None:
        """停止シグナルをチェックしながらキューからタスクを取得する.

        Args:
            timeout: タイムアウト時間(秒)。Noneの場合は無期限待機
            signal_checker: 停止シグナルをチェックするコールバック関数
                           Trueを返した場合は即座にNoneを返す
            poll_interval: シグナルチェック間隔(秒)

        Returns:
            取得したタスクの辞書。タイムアウトまたは停止シグナル検出時はNone

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

    def get_with_signal_check(
        self,
        timeout: float | None = None,
        signal_checker: Callable[[], bool] | None = None,
        poll_interval: float = 1.0,
    ) -> dict[str, Any] | None:
        """停止シグナルをチェックしながらキューからタスクを取得する.

        Args:
            timeout: タイムアウト時間(秒)。Noneの場合は無期限待機
            signal_checker: 停止シグナルをチェックするコールバック関数
            poll_interval: シグナルチェック間隔(秒)

        Returns:
            取得したタスクの辞書。タイムアウトまたは停止シグナル検出時はNone

        """
        # タイムアウトがNoneの場合は無期限待機
        if timeout is None:
            while True:
                # 停止シグナルをチェック
                if signal_checker and signal_checker():
                    return None
                try:
                    return self.queue.get(timeout=poll_interval)
                except Empty:
                    continue
        else:
            # タイムアウトが指定されている場合
            elapsed = 0.0
            while elapsed < timeout:
                # 停止シグナルをチェック
                if signal_checker and signal_checker():
                    return None
                # 残り時間を計算
                remaining = timeout - elapsed
                wait_time = min(poll_interval, remaining)
                try:
                    return self.queue.get(timeout=wait_time)
                except Empty:
                    elapsed += wait_time
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
        body = json.dumps(task)
        try:
            self.channel.basic_publish(
                exchange="",
                routing_key=self.queue_name,
                body=body,
                properties=pika.BasicProperties(delivery_mode=2),
            )
        except pika.exceptions.StreamLostError:
            self._reconnect()
            self.put(task)

    def _reconnect(self) -> None:
        """RabbitMQサーバーへ再接続する."""
        credentials = pika.PlainCredentials(self.user, self.password)
        self.connection = pika.BlockingConnection(
            pika.ConnectionParameters(
                host=self.host, port=self.port, credentials=credentials,
            ),
        )
        self.channel = self.connection.channel()
        self.channel.queue_declare(queue=self.queue_name, durable=True)

    def get(self, timeout: float | None = None) -> dict[str, Any] | None:  # noqa: ARG002
        """RabbitMQキューからタスクを取得する.

        タイムアウトが指定されている場合、ポーリングでタイムアウト制御を行う。

        Args:
            timeout: タイムアウト時間(秒)。Noneの場合は即座にチェックして返す

        Returns:
            取得したタスクの辞書。メッセージがない場合またはタイムアウト時はNone

        """
        return self._get_once()

    def _get_once(self) -> dict[str, Any] | None:
        """キューからメッセージを1回取得する."""
        try:
            method_frame, _header_frame, body = self.channel.basic_get(
                queue=self.queue_name, auto_ack=True,
            )
        except pika.exceptions.StreamLostError:
            self._reconnect()
            return self._get_once()
        else:
            if method_frame:
                return json.loads(body)
            return None

    def get_with_signal_check(
        self,
        timeout: float | None = None,
        signal_checker: Callable[[], bool] | None = None,
        poll_interval: float = 1.0,
    ) -> dict[str, Any] | None:
        """停止シグナルをチェックしながらキューからタスクを取得する.

        Args:
            timeout: タイムアウト時間(秒)。Noneの場合は無期限待機
            signal_checker: 停止シグナルをチェックするコールバック関数
            poll_interval: シグナルチェック間隔(秒)

        Returns:
            取得したタスクの辞書。タイムアウトまたは停止シグナル検出時はNone

        """
        # タイムアウトがNoneの場合は無期限待機
        if timeout is None:
            while True:
                # 停止シグナルをチェック
                if signal_checker and signal_checker():
                    return None
                # キューから取得を試行
                result = self._get_once()
                if result is not None:
                    return result
                # 待機
                time.sleep(poll_interval)
        else:
            # タイムアウトが指定されている場合
            elapsed = 0.0
            while elapsed < timeout:
                # 停止シグナルをチェック
                if signal_checker and signal_checker():
                    return None
                # キューから取得を試行
                result = self._get_once()
                if result is not None:
                    return result
                # 残り時間を計算
                remaining = timeout - elapsed
                wait_time = min(poll_interval, remaining)
                time.sleep(wait_time)
                elapsed += wait_time
            return None

    def empty(self) -> bool:
        """RabbitMQキューが空かどうかを確認する.

        Returns:
            キューが空の場合True、そうでなければFalse

        """
        try:
            queue_info = self.channel.queue_declare(queue=self.queue_name, passive=True)
            queue_info = self.channel.queue_declare(queue=self.queue_name, passive=True)
        except pika.exceptions.StreamLostError:
            self._reconnect()
            return self.empty()
        else:
            return queue_info.method.message_count == 0
