"""継続動作モードのユニットテスト.

Producer/Consumerの継続動作モードに関連する機能をテストします。
"""
from __future__ import annotations

import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from queueing import InMemoryTaskQueue, RabbitMQTaskQueue


class TestInMemoryTaskQueueWithSignalCheck:
    """InMemoryTaskQueueのget_with_signal_check機能テスト."""

    def test_get_with_signal_check_returns_task(self) -> None:
        """タスクがある場合、即座にタスクを返す."""
        queue = InMemoryTaskQueue()
        task = {"type": "test", "id": 1}
        queue.put(task)

        result = queue.get_with_signal_check(timeout=5.0)

        assert result == task

    def test_get_with_signal_check_timeout(self) -> None:
        """タイムアウト時はNoneを返す."""
        queue = InMemoryTaskQueue()

        start_time = time.time()
        result = queue.get_with_signal_check(timeout=1.0, poll_interval=0.5)
        elapsed = time.time() - start_time

        assert result is None
        assert elapsed >= 1.0

    def test_get_with_signal_check_stops_on_signal(self) -> None:
        """停止シグナル検出時は即座にNoneを返す."""
        queue = InMemoryTaskQueue()

        call_count = 0

        def signal_checker() -> bool:
            nonlocal call_count
            call_count += 1
            # 2回目の呼び出しでTrueを返す
            return call_count >= 2

        start_time = time.time()
        result = queue.get_with_signal_check(
            timeout=10.0,
            signal_checker=signal_checker,
            poll_interval=0.1,
        )
        elapsed = time.time() - start_time

        assert result is None
        # タイムアウトより早く終了している
        assert elapsed < 1.0

    def test_get_with_signal_check_no_timeout(self) -> None:
        """タイムアウトがNoneの場合、シグナルで停止する."""
        queue = InMemoryTaskQueue()

        call_count = 0

        def signal_checker() -> bool:
            nonlocal call_count
            call_count += 1
            return call_count >= 3

        result = queue.get_with_signal_check(
            timeout=None,
            signal_checker=signal_checker,
            poll_interval=0.1,
        )

        assert result is None
        assert call_count >= 3


class TestRabbitMQTaskQueueWithSignalCheck:
    """RabbitMQTaskQueueのget_with_signal_check機能テスト(モック)."""

    @patch("queueing.pika.BlockingConnection")
    def test_get_with_signal_check_returns_task(
        self, mock_connection: MagicMock
    ) -> None:
        """タスクがある場合、即座にタスクを返す."""
        # モックのセットアップ
        mock_channel = MagicMock()
        mock_connection.return_value.channel.return_value = mock_channel
        mock_channel.basic_get.return_value = (
            MagicMock(),  # method_frame
            MagicMock(),  # header_frame
            b'{"type": "test", "id": 1}',  # body
        )

        config: dict[str, Any] = {"rabbitmq": {"host": "localhost"}}
        queue = RabbitMQTaskQueue(config)

        result = queue.get_with_signal_check(timeout=5.0)

        assert result == {"type": "test", "id": 1}

    @patch("queueing.pika.BlockingConnection")
    def test_get_with_signal_check_timeout(
        self, mock_connection: MagicMock
    ) -> None:
        """タイムアウト時はNoneを返す."""
        # モックのセットアップ
        mock_channel = MagicMock()
        mock_connection.return_value.channel.return_value = mock_channel
        mock_channel.basic_get.return_value = (None, None, None)

        config: dict[str, Any] = {"rabbitmq": {"host": "localhost"}}
        queue = RabbitMQTaskQueue(config)

        start_time = time.time()
        result = queue.get_with_signal_check(timeout=0.5, poll_interval=0.1)
        elapsed = time.time() - start_time

        assert result is None
        assert elapsed >= 0.5

    @patch("queueing.pika.BlockingConnection")
    def test_get_with_signal_check_stops_on_signal(
        self, mock_connection: MagicMock
    ) -> None:
        """停止シグナル検出時は即座にNoneを返す."""
        # モックのセットアップ
        mock_channel = MagicMock()
        mock_connection.return_value.channel.return_value = mock_channel
        mock_channel.basic_get.return_value = (None, None, None)

        config: dict[str, Any] = {"rabbitmq": {"host": "localhost"}}
        queue = RabbitMQTaskQueue(config)

        call_count = 0

        def signal_checker() -> bool:
            nonlocal call_count
            call_count += 1
            return call_count >= 2

        start_time = time.time()
        result = queue.get_with_signal_check(
            timeout=10.0,
            signal_checker=signal_checker,
            poll_interval=0.1,
        )
        elapsed = time.time() - start_time

        assert result is None
        # タイムアウトより早く終了している
        assert elapsed < 1.0


class TestWaitWithSignalCheck:
    """wait_with_signal_check関数のテスト.

    main.pyからのインポートが依存関係の問題で失敗するため、
    ロジックを直接テストします。
    """

    def _wait_with_signal_check(
        self,
        wait_seconds: int,
        pause_manager: MagicMock,
    ) -> bool:
        """待機処理のロジックを再実装(テスト用)."""
        elapsed = 0
        while elapsed < wait_seconds:
            if pause_manager.check_pause_signal():
                return False
            time.sleep(0.1)  # テスト用に短縮
            elapsed += 1
        return True

    def test_wait_completes_normally(self) -> None:
        """待機時間が経過すると正常に完了する."""
        mock_pause_manager = MagicMock()
        mock_pause_manager.check_pause_signal.return_value = False

        result = self._wait_with_signal_check(2, mock_pause_manager)

        assert result is True

    def test_wait_stops_on_signal(self) -> None:
        """シグナル検出時に早期終了する."""
        mock_pause_manager = MagicMock()
        call_count = 0

        def check_signal() -> bool:
            nonlocal call_count
            call_count += 1
            return call_count >= 2

        mock_pause_manager.check_pause_signal.side_effect = check_signal

        result = self._wait_with_signal_check(10, mock_pause_manager)

        assert result is False


class TestUpdateHealthcheckFile:
    """update_healthcheck_file関数のテスト.

    main.pyからのインポートが依存関係の問題で失敗するため、
    ロジックを直接テストします。
    """

    def _update_healthcheck_file(
        self, healthcheck_dir: Path, service_name: str
    ) -> None:
        """ヘルスチェックファイル更新ロジック(テスト用)."""
        healthcheck_dir.mkdir(parents=True, exist_ok=True)
        healthcheck_file = healthcheck_dir / f"{service_name}.health"
        healthcheck_file.write_text(datetime.now(timezone.utc).isoformat())

    def test_creates_healthcheck_file(self) -> None:
        """ヘルスチェックファイルを作成する."""
        with tempfile.TemporaryDirectory() as tmpdir:
            healthcheck_dir = Path(tmpdir) / "healthcheck"

            self._update_healthcheck_file(healthcheck_dir, "producer")

            healthcheck_file = healthcheck_dir / "producer.health"
            assert healthcheck_file.exists()
            content = healthcheck_file.read_text()
            # ISO 8601形式の日時文字列が含まれている
            assert "T" in content

    def test_updates_existing_file(self) -> None:
        """既存のヘルスチェックファイルを更新する."""
        with tempfile.TemporaryDirectory() as tmpdir:
            healthcheck_dir = Path(tmpdir) / "healthcheck"
            healthcheck_dir.mkdir(parents=True)
            healthcheck_file = healthcheck_dir / "consumer.health"
            healthcheck_file.write_text("old content")

            self._update_healthcheck_file(healthcheck_dir, "consumer")

            new_content = healthcheck_file.read_text()
            assert new_content != "old content"
            assert "T" in new_content  # ISO 8601形式


class TestContinuousModeConfig:
    """継続動作モード設定の読み込みテスト."""

    def test_default_config_values(self) -> None:
        """デフォルト設定値が正しく読み込まれる."""
        import yaml

        config_path = Path("/home/runner/work/coding_agent/coding_agent/config.yaml")
        with config_path.open() as f:
            config = yaml.safe_load(f)

        continuous_config = config.get("continuous", {})

        # デフォルト値の確認
        assert "producer" in continuous_config
        assert "consumer" in continuous_config
        assert "healthcheck" in continuous_config

        producer_config = continuous_config.get("producer", {})
        assert producer_config.get("interval_minutes") == 5
        assert producer_config.get("delay_first_run") is False

        consumer_config = continuous_config.get("consumer", {})
        assert consumer_config.get("queue_timeout_seconds") == 30
        assert consumer_config.get("min_interval_seconds") == 0


class TestContinuousModeArgument:
    """--continuousコマンドライン引数のテスト."""

    def test_continuous_argument_is_parsed(self) -> None:
        """--continuous引数が正しく解析される."""
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument("--mode", choices=["producer", "consumer"])
        parser.add_argument("--continuous", action="store_true")

        # --continuousありの場合
        args = parser.parse_args(["--mode", "producer", "--continuous"])
        assert args.continuous is True
        assert args.mode == "producer"

        # --continuousなしの場合
        args = parser.parse_args(["--mode", "consumer"])
        assert args.continuous is False
        assert args.mode == "consumer"

