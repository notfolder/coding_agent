"""コーディングエージェントのメインエントリーポイント.

このモジュールは、GitHubやGitLabからタスクを取得し、LLMを使用して
自動的に処理を行うコーディングエージェントのメイン処理を含みます。
"""
from __future__ import annotations

import argparse
import logging
import logging.config
import os
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
import yaml

from clients.lm_client import get_llm_client
from clients.mcp_tool_client import MCPToolClient
from filelock_util import FileLock
from handlers.task_getter import TaskGetter
from handlers.task_handler import TaskHandler
from pause_resume_manager import PauseResumeManager
from queueing import InMemoryTaskQueue, RabbitMQTaskQueue



def setup_logger() -> None:
    """ログ設定を初期化する.

    環境変数から取得したログレベルとログファイルパスを使用して
    ログ設定を行います。DEBUG環境変数がtrueの場合はDEBUGレベル、
    そうでなければINFOレベルでログを出力します。
    """
    # 環境変数からログファイルのパスを取得(デフォルト: logs/agent.log)
    log_path = os.environ.get("LOGS", "logs/agent.log")

    # DEBUG環境変数の値に基づいてログレベルを決定
    loglevel = "DEBUG" if os.environ.get("DEBUG", "").lower() == "true" else "INFO"

    # logging.confファイルからログ設定を読み込み
    logging.config.fileConfig(
        "logging.conf",
        defaults={"LOGS": log_path, "loglevel": loglevel},
        disable_existing_loggers=False,
    )


def load_config(config_file: str = "config.yaml") -> dict[str, Any]:
    """設定ファイルを読み込み、環境変数で上書きする.

    指定された設定ファイルを読み込み、環境変数で定義された値で
    設定を上書きします。LLM、MCP、RabbitMQ等の設定が対象です。
    
    USE_USER_CONFIG_API環境変数がtrueの場合、API経由で設定を取得します。

    Args:
        config_file: 読み込む設定ファイルのパス

    Returns:
        読み込まれた設定の辞書

    Raises:
        FileNotFoundError: 設定ファイルが見つからない場合
        yaml.YAMLError: YAMLの解析に失敗した場合

    """
    # ロガー取得
    logger = logging.getLogger(__name__)
    
    # 設定ファイルを読み込み
    with Path(config_file).open() as f:
        config = yaml.safe_load(f)
    
    # 環境変数による設定上書きを先に実行
    _override_mcp_config(config)
    _override_rabbitmq_config(config)
    _override_bot_config(config)
    
    # API経由でLLM設定を取得するかチェック
    use_api = os.environ.get("USE_USER_CONFIG_API", "false").lower() == "true"
    
    if use_api:
        try:
            config = _fetch_config_from_api(config, logger)
        except (requests.ConnectionError, requests.Timeout) as e:
            logger.exception(f"API接続エラー、設定ファイルを使用{e}")
        except (ValueError, requests.HTTPError) as e:
            logger.exception(f"API設定取得エラー、設定ファイルを使用{e}")
        except Exception as e:
            logger.exception(f"予期しないエラー、設定ファイルを使用{e}")
    
    # LLM設定を環境変数で最終的に上書き
    _override_llm_config(config)

    return config


def _fetch_config_from_api(
    config: dict[str, Any], logger: logging.Logger, username: str | None = None
) -> dict[str, Any]:
    """API経由で設定を取得する.
    
    Args:
        config: ベースとなる設定辞書
        logger: ロガー
        username: ユーザー名（Noneの場合はconfig.yamlから取得）
    
    Returns:
        API設定でマージされた設定辞書
    
    Raises:
        ValueError: 設定エラーまたはAPI呼び出しエラー
    """
    # タスクソースを取得
    task_source = os.environ.get("TASK_SOURCE", "github")
    
    # ユーザー名が指定されていない場合はconfig.yamlから取得
    if username is None:
        if task_source == "github":
            username = config.get("github", {}).get("owner", "")
        elif task_source == "gitlab":
            username = config.get("gitlab", {}).get("owner", "")
        else:
            raise ValueError(f"Unknown task source: {task_source}")
    
    # APIエンドポイントとAPIキー
    api_url = os.environ.get("USER_CONFIG_API_URL", "http://user-config-api:8080")
    api_key = os.environ.get("USER_CONFIG_API_KEY", "")
    
    if not api_key:
        raise ValueError("USER_CONFIG_API_KEY is not set")
    
    url = f"{api_url}/config/{task_source}/{username}"
    
    # Bearer トークンとしてAPIキーをヘッダーに含めて呼び出し
    headers = {"Authorization": f"Bearer {api_key}"}
    response = requests.get(url, headers=headers, timeout=5)
    response.raise_for_status()

    data = response.json()
    if data.get("status") == "success":
        # API設定を取得
        api_data = data["data"]
        
        # LLM設定を上書き
        config["llm"] = api_data["llm"]
        
        # システムプロンプトを上書き（環境変数で上書きされていない場合のみ）
        if "system_prompt" in api_data:
            config["system_prompt"] = api_data["system_prompt"]
        
        logger.info(f"API経由でLLM設定を取得: {task_source}:{username}")
    else:
        raise ValueError(f"API returned error: {data.get('message')}")
    
    return config


def fetch_user_config(task: Any, base_config: dict[str, Any]) -> dict[str, Any]:
    """タスクのユーザーに基づいて設定を取得する.

    USE_USER_CONFIG_API環境変数がtrueの場合、タスクの作成者のユーザー名を使用して
    API経由で設定を取得します。そうでない場合はbase_configをそのまま返します。

    Args:
        task: タスクオブジェクト（issue/PR/MRの情報を含む）
        base_config: ベースとなる設定辞書

    Returns:
        ユーザー設定でマージされた設定辞書
    """
    # API使用フラグをチェック
    use_api = os.environ.get("USE_USER_CONFIG_API", "false").lower() == "true"
    if not use_api:
        return base_config

    # タスクからユーザー名を取得
    try:
        username = task.get_user()

        if not username:
            # ユーザー名が取得できない場合はベース設定を使用
            logger = logging.getLogger(__name__)
            logger.warning("タスクからユーザー名を取得できませんでした。デフォルト設定を使用します。")
            return base_config

        # API経由で設定を取得
        logger = logging.getLogger(__name__)
        return _fetch_config_from_api(base_config.copy(), logger, username)

    except (ValueError, TypeError, AttributeError) as e:
        # エラーが発生した場合はベース設定を使用
        logger = logging.getLogger(__name__)
        logger.warning("ユーザー設定の取得に失敗しました: %s。デフォルト設定を使用します。", e)
        return base_config



def _override_llm_config(config: dict[str, Any]) -> None:
    """LLM設定を環境変数で上書きする."""
    # function_calling設定の処理
    function_calling = os.environ.get("FUNCTION_CALLING", "true").lower() == "true"
    if "llm" in config:
        config["llm"]["function_calling"] = function_calling

    # LLMプロバイダー設定の処理
    llm_provider = os.environ.get("LLM_PROVIDER")
    if llm_provider and "llm" in config and "provider" in config["llm"]:
        config["llm"]["provider"] = llm_provider

    # LM Studio設定の上書き処理
    _override_lmstudio_config(config)

    # Ollama設定の上書き処理
    _override_ollama_config(config)

    # OpenAI設定の上書き処理
    _override_openai_config(config)


def _override_lmstudio_config(config: dict[str, Any]) -> None:
    """LM Studio設定を環境変数で上書きする."""
    lmstudio_env_url = os.environ.get("LMSTUDIO_BASE_URL")
    if lmstudio_env_url and "llm" in config and "lmstudio" in config["llm"]:
        config["llm"]["lmstudio"]["base_url"] = lmstudio_env_url

    lmstudio_env_model = os.environ.get("LMSTUDIO_MODEL")
    if lmstudio_env_model and "llm" in config and "lmstudio" in config["llm"]:
        config["llm"]["lmstudio"]["model"] = lmstudio_env_model


def _override_ollama_config(config: dict[str, Any]) -> None:
    """Ollama設定を環境変数で上書きする."""
    ollama_env_endpoint = os.environ.get("OLLAMA_ENDPOINT")
    if ollama_env_endpoint and "llm" in config and "ollama" in config["llm"]:
        config["llm"]["ollama"]["endpoint"] = ollama_env_endpoint

    ollama_env_model = os.environ.get("OLLAMA_MODEL")
    if ollama_env_model and "llm" in config and "ollama" in config["llm"]:
        config["llm"]["ollama"]["model"] = ollama_env_model


def _override_openai_config(config: dict[str, Any]) -> None:
    """OpenAI設定を環境変数で上書きする."""
    openai_env_base_url = os.environ.get("OPENAI_BASE_URL")
    if openai_env_base_url and "llm" in config and "openai" in config["llm"]:
        config["llm"]["openai"]["base_url"] = openai_env_base_url

    openai_env_model = os.environ.get("OPENAI_MODEL")
    if openai_env_model and "llm" in config and "openai" in config["llm"]:
        config["llm"]["openai"]["model"] = openai_env_model

    openai_env_key = os.environ.get("OPENAI_API_KEY")
    if openai_env_key and "llm" in config and "openai" in config["llm"]:
        config["llm"]["openai"]["api_key"] = openai_env_key


def _override_mcp_config(config: dict[str, Any]) -> None:
    """MCP設定を環境変数で上書きする."""
    logger = logging.getLogger(__name__)
    
    # GitHub MCPコマンド設定の処理
    github_cmd_env = os.environ.get("GITHUB_MCP_COMMAND")
    if github_cmd_env:
        for server in config.get("mcp_servers", []):
            if server.get("mcp_server_name") == "github":
                # スペース区切りで分割してコマンドリストを作成
                server["command"] = github_cmd_env.split()

    # 全MCPサーバーの環境変数を上書き
    for server in config.get("mcp_servers", []):
        server_name = server.get("mcp_server_name", "unknown")
        logger.debug("MCP Server: %s, command: %s", server_name, server.get("command"))
        
        if "env" not in server:
            continue
        
        # 環境変数の上書き処理（空文字列のキーは削除）
        keys_to_remove = []
        for key in list(server["env"].keys()):
            env_value = os.environ.get(key)
            if env_value is not None and env_value != "":
                # 環境変数が設定されている場合は上書き
                value_display = f"{env_value[:20]}..." if len(env_value) > 20 else env_value
                logger.debug("  %s: %s=%s", server_name, key, value_display)
                server["env"][key] = env_value
            elif server["env"][key] == "":
                # config.yamlで空文字列の場合は削除対象
                logger.debug("  %s: %s=<not set, removing>", server_name, key)
                keys_to_remove.append(key)
            else:
                # config.yamlに値がある場合はそのまま
                logger.debug("  %s: %s=<using config value>", server_name, key)
        
        # 空文字列のキーを削除
        for key in keys_to_remove:
            del server["env"][key]


def _override_rabbitmq_config(config: dict[str, Any]) -> None:
    """RabbitMQ設定を環境変数で上書きする."""
    rabbitmq_env = {
        "host": os.environ.get("RABBITMQ_HOST"),
        "port": os.environ.get("RABBITMQ_PORT"),
        "user": os.environ.get("RABBITMQ_USER"),
        "password": os.environ.get("RABBITMQ_PASSWORD"),
        "queue": os.environ.get("RABBITMQ_QUEUE"),
    }

    # RabbitMQ設定の初期化と上書き
    if "rabbitmq" not in config:
        config["rabbitmq"] = {}
    for k, v in rabbitmq_env.items():
        if v is not None:
            config["rabbitmq"][k] = v

    # RabbitMQポート番号の型変換処理
    if "port" in config["rabbitmq"] and config["rabbitmq"]["port"] is not None:
        try:
            config["rabbitmq"]["port"] = int(config["rabbitmq"]["port"])
        except (ValueError, TypeError, KeyError):
            # 変換に失敗した場合はデフォルトポート番号を使用
            config["rabbitmq"]["port"] = 5672

    # RabbitMQキュー名のデフォルト値設定
    if "queue" in config["rabbitmq"] and not config["rabbitmq"]["queue"]:
        config["rabbitmq"]["queue"] = "mcp_tasks"


def _override_bot_config(config: dict[str, Any]) -> None:
    """ボット名設定を環境変数で上書きする."""
    github_bot_name = os.environ.get("GITHUB_BOT_NAME")
    if github_bot_name and "github" in config and isinstance(config["github"], dict):
        config["github"]["assignee"] = github_bot_name

    gitlab_bot_name = os.environ.get("GITLAB_BOT_NAME")
    if gitlab_bot_name and "gitlab" in config and isinstance(config["gitlab"], dict):
        config["gitlab"]["assignee"] = gitlab_bot_name


def produce_tasks(
    config: dict[str, Any],
    mcp_clients: dict[str, MCPToolClient],
    task_source: str,
    task_queue: RabbitMQTaskQueue | InMemoryTaskQueue,
    logger: logging.Logger,
) -> None:
    """タスクを取得してキューに追加する.

    指定されたタスクソース(GitHubまたはGitLab)からタスクを取得し、
    各タスクの準備処理を実行してからキューに追加します。
    また、一時停止中のタスクを検出してキューに再投入します。

    Args:
        config: アプリケーション設定辞書
        mcp_clients: MCPクライアントの辞書
        task_source: タスクソース("github" または "gitlab")
        task_queue: タスクキューオブジェクト
        logger: ログ出力用のロガー

    """
    # タスクゲッターのファクトリーメソッドでインスタンス生成
    task_getter = TaskGetter.factory(config, mcp_clients, task_source)

    # 一時停止タスクの検出と再投入
    pause_manager = PauseResumeManager(config)
    paused_tasks = pause_manager.get_paused_tasks()

    paused_count = 0
    for task_state in paused_tasks:
        # Validate task still exists on GitHub/GitLab
        try:
            task_dict_temp = task_state["task_key"]
            task = task_getter.from_task_key(task_dict_temp)

            if task is None:
                logger.warning("一時停止タスクが見つかりません(削除済み): %s", task_state.get("uuid"))
                continue

            # Prepare task dictionary for resuming
            task_dict = pause_manager.prepare_resume_task_dict(task_state)
            task_queue.put(task_dict)
            paused_count += 1
            logger.info("一時停止タスクをキューに再投入しました: %s", task_state.get("uuid"))
        except Exception:
            logger.exception(
                "一時停止タスクの再投入エラー: uuid=%s", task_state.get("uuid")
            )

    if paused_count > 0:
        logger.info("%d件の一時停止タスクをキューに再投入しました", paused_count)

    # タスクリストを取得
    tasks = task_getter.get_task_list()

    # 各タスクの準備処理を実行してキューに追加
    for task in tasks:
        task.prepare()  # ラベル付与などの準備処理
        task_dict = task.get_task_key().to_dict()
        task_dict["uuid"] = str(uuid.uuid4())  # UUID v4を生成して追加
        task_dict["user"] = task.get_user()    # ユーザー情報も追加
        task_queue.put(task_dict)

    logger.info("%d件のタスクをキューに追加しました", len(tasks))


def consume_tasks(
    task_queue: RabbitMQTaskQueue | InMemoryTaskQueue,
    handler: TaskHandler,
    logger: logging.Logger,
    task_config: dict[str, Any],
) -> None:
    """キューからタスクを取得して処理する.

    タスクキューからタスクを取得し、TaskHandlerを使用して
    各タスクを順次処理します。処理できないタスクはスキップされます。

    Args:
        task_queue: タスクキューオブジェクト
        handler: タスク処理ハンドラー
        logger: ログ出力用のロガー
        task_config: タスク設定情報(mcp_clients, config, task_sourceを含む)

    """
    # 設定から必要な情報を取得
    mcp_clients = task_config["mcp_clients"]
    config = task_config["config"]
    task_source = task_config["task_source"]

    # タスクゲッターのファクトリーメソッドでインスタンス生成
    task_getter = TaskGetter.factory(config, mcp_clients, task_source)

    while True:
        # キューからタスクキーを取得
        task_key_dict = task_queue.get()
        if task_key_dict is None:
            # タイムアウトした場合はループを終了
            break

        # TaskGetterのfrom_task_keyメソッドでTaskインスタンスを生成
        task = task_getter.from_task_key(task_key_dict)
        if task is None:
            logger.error("Unknown or invalid task key: %s", task_key_dict)
            continue

        # UUIDとユーザー情報をタスクに設定
        task.uuid = task_key_dict.get("uuid")
        task.user = task_key_dict.get("user")
        
        # Check if this is a resumed task
        task.is_resumed = task_key_dict.get("is_resumed", False)

        # タスクの状態確認（再開タスクの場合はスキップ）
        if not task.is_resumed:
            if not hasattr(task, "check") or not task.check():
                logger.info("スキップ: processing_labelが付与されていないタスク %s", task_key_dict)
                continue
        else:
            logger.info("再開タスクを処理します: %s", task_key_dict.get("uuid"))

        # タスクの処理実行
        try:
            handler.handle(task)
        except Exception as e:
            logger.exception("Task処理中にエラー")
            # エラーが発生した場合はタスクにコメントを追加
            task.comment(f"処理中にエラーが発生しました: {e}")


def update_healthcheck_file(healthcheck_dir: Path, service_name: str) -> None:
    """ヘルスチェックファイルを更新する.

    Args:
        healthcheck_dir: ヘルスチェックディレクトリ
        service_name: サービス名 (producer または consumer)

    """
    # ディレクトリを作成
    healthcheck_dir.mkdir(parents=True, exist_ok=True)
    # ヘルスチェックファイルを更新
    healthcheck_file = healthcheck_dir / f"{service_name}.health"
    healthcheck_file.write_text(datetime.now(timezone.utc).isoformat())


def wait_with_signal_check(
    wait_seconds: int,
    pause_manager: PauseResumeManager,
    logger: logging.Logger,
) -> bool:
    """停止シグナルをチェックしながら指定時間待機する.

    Args:
        wait_seconds: 待機時間(秒)
        pause_manager: PauseResumeManagerインスタンス
        logger: ロガー

    Returns:
        True: 待機完了、False: 停止シグナル検出

    """
    elapsed = 0
    while elapsed < wait_seconds:
        # 停止シグナルをチェック
        if pause_manager.check_pause_signal():
            logger.info("停止シグナルを検出しました")
            return False
        # 1秒待機
        time.sleep(1)
        elapsed += 1
    return True


def run_producer_continuous(
    config: dict[str, Any],
    mcp_clients: dict[str, MCPToolClient],
    task_source: str,
    task_queue: RabbitMQTaskQueue | InMemoryTaskQueue,
    logger: logging.Logger,
) -> None:
    """Producer継続動作モードを実行する.

    タスク取得を継続的に実行し、指定間隔で待機します。
    停止シグナルを検出するとgracefulに終了します。

    Args:
        config: アプリケーション設定辞書
        mcp_clients: MCPクライアントの辞書
        task_source: タスクソース
        task_queue: タスクキューオブジェクト
        logger: ロガー

    """
    from handlers.execution_environment_manager import ExecutionEnvironmentManager

    # 継続動作モード設定を取得
    continuous_config = config.get("continuous", {})
    producer_config = continuous_config.get("producer", {})
    interval_minutes = producer_config.get("interval_minutes", 1)
    delay_first_run = producer_config.get("delay_first_run", False)
    interval_seconds = interval_minutes * 60

    # ヘルスチェック設定
    healthcheck_config = continuous_config.get("healthcheck", {})
    healthcheck_dir = Path(healthcheck_config.get("dir", "healthcheck"))
    healthcheck_interval = healthcheck_config.get("update_interval_seconds", 60)

    # PauseResumeManager初期化
    pause_manager = PauseResumeManager(config)

    # ExecutionEnvironmentManager初期化（残存コンテナクリーンアップ用）
    execution_manager = ExecutionEnvironmentManager(config)
    cleanup_config = config.get("command_executor", {}).get("cleanup", {})
    cleanup_interval_hours = cleanup_config.get("interval_hours", 24)
    cleanup_interval_seconds = cleanup_interval_hours * 3600
    last_cleanup = 0.0

    logger.info("継続動作モードで起動しました(Producer)")
    logger.info("タスク取得間隔: %d分", interval_minutes)

    loop_count = 0
    last_healthcheck = 0.0

    # 初回実行を遅延させる場合
    if delay_first_run:
        logger.info("初回実行を%d分遅延します", interval_minutes)
        if not wait_with_signal_check(interval_seconds, pause_manager, logger):
            logger.info("継続動作モードを終了しました(Producer)")
            return

    # 起動時に残存コンテナをクリーンアップ
    if execution_manager.is_enabled():
        try:
            deleted = execution_manager.cleanup_stale_containers()
            if deleted > 0:
                logger.info("起動時の残存コンテナクリーンアップ: %d件削除", deleted)
        except Exception:
            logger.exception("起動時の残存コンテナクリーンアップに失敗")

    lock_path = Path(tempfile.gettempdir()) / "produce_tasks.lock"

    while True:
        loop_count += 1

        # ヘルスチェックファイル更新
        current_time = time.time()
        if current_time - last_healthcheck >= healthcheck_interval:
            update_healthcheck_file(healthcheck_dir, "producer")
            last_healthcheck = current_time

        # 残存コンテナの定期クリーンアップ
        if execution_manager.is_enabled() and current_time - last_cleanup >= cleanup_interval_seconds:
            try:
                deleted = execution_manager.cleanup_stale_containers()
                if deleted > 0:
                    logger.info("定期クリーンアップ: %d件の残存コンテナを削除", deleted)
                last_cleanup = current_time
            except Exception:
                logger.exception("残存コンテナのクリーンアップに失敗")

        # 停止シグナルをチェック
        if pause_manager.check_pause_signal():
            logger.info("停止シグナルを検出しました")
            break

        logger.info("タスク取得処理を開始します(ループ回数: %d)", loop_count)

        # タスク取得処理(ファイルロック付き)
        try:
            with FileLock(str(lock_path)):
                produce_tasks(config, mcp_clients, task_source, task_queue, logger)
        except Exception:
            logger.exception("タスク取得処理中にエラーが発生しました")

        logger.info("次のタスク取得まで%d分待機します", interval_minutes)

        # 指定時間待機(シグナルチェック付き)
        if not wait_with_signal_check(interval_seconds, pause_manager, logger):
            break

    logger.info("継続動作モードを終了しました(Producer)")


def run_consumer_continuous(
    task_queue: RabbitMQTaskQueue | InMemoryTaskQueue,
    handler: TaskHandler,
    logger: logging.Logger,
    task_config: dict[str, Any],
) -> None:
    """Consumer継続動作モードを実行する.

    キューからタスクを継続的に取得して処理します。
    停止シグナルを検出するとgracefulに終了します。

    Args:
        task_queue: タスクキューオブジェクト
        handler: タスク処理ハンドラー
        logger: ロガー
        task_config: タスク設定情報

    """
    # 設定を取得
    config = task_config["config"]
    mcp_clients = task_config["mcp_clients"]
    task_source = task_config["task_source"]

    # 継続動作モード設定を取得
    continuous_config = config.get("continuous", {})
    consumer_config = continuous_config.get("consumer", {})
    queue_timeout = consumer_config.get("queue_timeout_seconds", 30)
    min_interval = consumer_config.get("min_interval_seconds", 0)

    # ヘルスチェック設定
    healthcheck_config = continuous_config.get("healthcheck", {})
    healthcheck_dir = Path(healthcheck_config.get("dir", "healthcheck"))
    healthcheck_interval = healthcheck_config.get("update_interval_seconds", 60)

    # PauseResumeManager初期化
    pause_manager = PauseResumeManager(config)

    # タスクゲッター初期化
    task_getter = TaskGetter.factory(config, mcp_clients, task_source)

    logger.info("継続動作モードで起動しました(Consumer)")
    logger.info("キュー取得タイムアウト: %d秒", queue_timeout)

    loop_count = 0
    last_healthcheck = 0.0

    while True:
        # ヘルスチェックファイル更新
        current_time = time.time()
        if current_time - last_healthcheck >= healthcheck_interval:
            update_healthcheck_file(healthcheck_dir, "consumer")
            last_healthcheck = current_time

        # 停止シグナルをチェック
        if pause_manager.check_pause_signal():
            logger.info("停止シグナルを検出しました")
            break

        loop_count += 1
        logger.debug("キューからタスク取得を試行します(ループ回数: %d)", loop_count)

        # タイムアウト付きでキューからタスク取得(シグナルチェック付き)
        task_key_dict = task_queue.get_with_signal_check(
            timeout=queue_timeout,
            signal_checker=pause_manager.check_pause_signal,
            poll_interval=1.0,
        )

        if task_key_dict is None:
            # タイムアウトまたはシグナル検出時
            if pause_manager.check_pause_signal():
                logger.info("停止シグナルを検出しました")
                break
            # タイムアウトの場合は継続
            continue

        # TaskGetterのfrom_task_keyメソッドでTaskインスタンスを生成
        task = task_getter.from_task_key(task_key_dict)
        if task is None:
            logger.error("Unknown or invalid task key: %s", task_key_dict)
            continue

        # UUIDとユーザー情報をタスクに設定
        task.uuid = task_key_dict.get("uuid")
        task.user = task_key_dict.get("user")

        # Check if this is a resumed task
        task.is_resumed = task_key_dict.get("is_resumed", False)

        # タスクの状態確認(再開タスクの場合はスキップ)
        if not task.is_resumed:
            if not hasattr(task, "check") or not task.check():
                logger.info("スキップ: processing_labelが付与されていないタスク %s", task_key_dict)
                continue
        else:
            logger.info("再開タスクを処理します: %s", task_key_dict.get("uuid"))

        # タスクの処理実行
        try:
            handler.handle(task)
        except Exception as e:
            logger.exception("Task処理中にエラー")
            # エラーが発生した場合はタスクにコメントを追加
            task.comment(f"処理中にエラーが発生しました: {e}")

        # 最小待機時間(レート制限用)
        if min_interval > 0:
            time.sleep(min_interval)

    logger.info("継続動作モードを終了しました(Consumer)")


def main() -> None:
    """メイン関数.

    コマンドライン引数を解析し、設定を読み込んで、
    プロデューサー・コンシューマーモードまたは統合モードで
    タスク処理を実行します。
    """
    # コマンドライン引数の解析
    parser = argparse.ArgumentParser(
        description="コーディングエージェント - GitHubやGitLabからタスクを自動処理",
    )
    parser.add_argument(
        "--mode",
        choices=["producer", "consumer"],
        help="producer: タスク取得のみ, consumer: キューから実行のみ",
    )
    parser.add_argument(
        "--continuous",
        action="store_true",
        help="継続動作モードを有効化(docker-compose用)",
    )
    args = parser.parse_args()

    # 標準出力・標準エラー出力のライン バッファリング設定
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)

    # ログ設定の初期化
    setup_logger()
    logger = logging.getLogger(__name__)

    # タスクソースの設定取得(デフォルト: "github")
    task_source = os.environ.get("TASK_SOURCE", "github")
    logger.info("TASK_SOURCE: %s", task_source)

    # 設定ファイルの読み込み (環境変数で指定可能、デフォルトはconfig.yaml)
    config_file = os.environ.get("CONFIG_FILE", "config.yaml")
    logger.info("設定ファイル: %s", config_file)
    config = load_config(config_file)

    # 継続動作モードの判定(コマンドラインオプション優先)
    continuous_mode = args.continuous or config.get("continuous", {}).get("enabled", False)
    if continuous_mode:
        logger.info("継続動作モード: 有効")

    # MCPサーバークライアントの初期化
    mcp_clients: dict[str, MCPToolClient] = {}
    functions: list[Any] | None = None
    tools: list[Any] | None = None

    # ファンクションコーリング設定の確認
    function_calling = config.get("llm", {}).get("function_calling", True)
    logger.info("function_calling: %s", function_calling)

    # ファンクションコーリングが有効な場合はリストを初期化
    if function_calling:
        functions = []
        tools = []

    # MCPサーバーの設定を順次処理
    for server in config.get("mcp_servers", []):
        name = server["mcp_server_name"]

        # タスクソースに応じて不要なMCPサーバーを除外
        # (例:タスクソースがgithubの場合、gitlabのMCPサーバーは除外)
        if name in ["github", "gitlab"] and name != task_source:
            continue

        # MCPツールクライアントを初期化
        mcp_clients[name] = MCPToolClient(
            server, function_calling=config.get("llm", {}).get("function_calling", True),
        )

        # ファンクションコーリングが有効な場合は関数とツールを取得
        if config.get("llm", {}).get("function_calling", True):
            functions.extend(mcp_clients[name].get_function_calling_functions())
            tools.extend(mcp_clients[name].get_function_calling_tools())

    # LLMクライアントの初期化
    llm_client = get_llm_client(config, functions, tools)

    # タスクキューの初期化 - RabbitMQまたはインメモリキューを使用
    task_queue = RabbitMQTaskQueue(config) if config.get("use_rabbitmq", False) else InMemoryTaskQueue()

    # タスクハンドラーの初期化
    handler = TaskHandler(llm_client, mcp_clients, config)

    # 実行モードに応じた処理の分岐
    lock_path = Path(tempfile.gettempdir()) / "produce_tasks.lock"
    if args.mode == "producer":
        if continuous_mode:
            # Producer継続動作モード
            run_producer_continuous(config, mcp_clients, task_source, task_queue, logger)
        else:
            # プロデューサーモード(単発実行)
            with FileLock(str(lock_path)):
                produce_tasks(config, mcp_clients, task_source, task_queue, logger)
        return
    if args.mode == "consumer":
        # コンシューマーモード
        task_config = {
            "mcp_clients": mcp_clients,
            "config": config,
            "task_source": task_source,
        }
        if continuous_mode:
            # Consumer継続動作モード
            run_consumer_continuous(task_queue, handler, logger, task_config)
        else:
            # 単発実行
            consume_tasks(task_queue, handler, logger, task_config)
    else:
        # デフォルトモード(producer + consumer)
        with FileLock(str(lock_path)):
            produce_tasks(config, mcp_clients, task_source, task_queue, logger)
        task_config = {
            "mcp_clients": mcp_clients,
            "config": config,
            "task_source": task_source,
        }
        consume_tasks(task_queue, handler, logger, task_config)


if __name__ == "__main__":
    main()
