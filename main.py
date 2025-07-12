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
from typing import Any

import yaml

from clients.lm_client import get_llm_client
from clients.mcp_tool_client import MCPToolClient
from filelock_util import FileLock
from handlers.task_factory import GitHubTaskFactory, GitLabTaskFactory
from handlers.task_getter import TaskGetter
from handlers.task_handler import TaskHandler
from handlers.task_key import (
    GitHubIssueTaskKey,
    GitHubPullRequestTaskKey,
    GitLabIssueTaskKey,
    GitLabMergeRequestTaskKey,
)
from queueing import InMemoryTaskQueue


def setup_logger() -> None:
    """ログ設定を初期化する.

    環境変数から取得したログレベルとログファイルパスを使用して
    ログ設定を行います。DEBUG環境変数がtrueの場合はDEBUGレベル、
    そうでなければINFOレベルでログを出力します。
    """
    import os

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

    Args:
        config_file: 読み込む設定ファイルのパス

    Returns:
        読み込まれた設定の辞書

    Raises:
        FileNotFoundError: 設定ファイルが見つからない場合
        yaml.YAMLError: YAMLの解析に失敗した場合

    """
    # 設定ファイルを読み込み
    with open(config_file) as f:
        config = yaml.safe_load(f)

    # function_calling設定の処理
    function_calling = os.environ.get("FUNCTION_CALLING", "true").lower() == "true"
    if "llm" in config:
        config["llm"]["function_calling"] = function_calling

    # LLMプロバイダー設定の処理
    llm_provider = os.environ.get("LLM_PROVIDER")
    if llm_provider and "llm" in config and "provider" in config["llm"]:
        config["llm"]["provider"] = llm_provider

    # LM Studio設定の上書き処理
    lmstudio_env_url = os.environ.get("LMSTUDIO_BASE_URL")
    if lmstudio_env_url and "llm" in config and "lmstudio" in config["llm"]:
        config["llm"]["lmstudio"]["base_url"] = lmstudio_env_url

    lmstudio_env_model = os.environ.get("LMSTUDIO_MODEL")
    if lmstudio_env_model and "llm" in config and "lmstudio" in config["llm"]:
        config["llm"]["lmstudio"]["model"] = lmstudio_env_model

    # Ollama設定の上書き処理
    ollama_env_endpoint = os.environ.get("OLLAMA_ENDPOINT")
    if ollama_env_endpoint and "llm" in config and "ollama" in config["llm"]:
        config["llm"]["ollama"]["endpoint"] = ollama_env_endpoint

    ollama_env_model = os.environ.get("OLLAMA_MODEL")
    if ollama_env_model and "llm" in config and "ollama" in config["llm"]:
        config["llm"]["ollama"]["model"] = ollama_env_model

    # OpenAI設定の上書き処理
    openai_env_base_url = os.environ.get("OPENAI_BASE_URL")
    if openai_env_base_url and "llm" in config and "openai" in config["llm"]:
        config["llm"]["openai"]["base_url"] = openai_env_base_url

    openai_env_model = os.environ.get("OPENAI_MODEL")
    if openai_env_model and "llm" in config and "openai" in config["llm"]:
        config["llm"]["openai"]["model"] = openai_env_model

    openai_env_key = os.environ.get("OPENAI_API_KEY")
    if openai_env_key and "llm" in config and "openai" in config["llm"]:
        config["llm"]["openai"]["api_key"] = openai_env_key

    # GitHub MCPコマンド設定の処理
    github_cmd_env = os.environ.get("GITHUB_MCP_COMMAND")
    if github_cmd_env:
        for server in config.get("mcp_servers", []):
            if server.get("mcp_server_name") == "github":
                # スペース区切りで分割してコマンドリストを作成
                server["command"] = github_cmd_env.split()

    # RabbitMQ設定の環境変数上書き処理
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
        except Exception:
            # 変換に失敗した場合はデフォルトポート番号を使用
            config["rabbitmq"]["port"] = 5672

    # RabbitMQキュー名のデフォルト値設定
    if "queue" in config["rabbitmq"] and not config["rabbitmq"]["queue"]:
        config["rabbitmq"]["queue"] = "mcp_tasks"

    # ボット名設定の処理(GitHub/GitLab)
    github_bot_name = os.environ.get("GITHUB_BOT_NAME")
    if github_bot_name and "github" in config and isinstance(config["github"], dict):
        config["github"]["assignee"] = github_bot_name

    gitlab_bot_name = os.environ.get("GITLAB_BOT_NAME")
    if gitlab_bot_name and "gitlab" in config and isinstance(config["gitlab"], dict):
        config["gitlab"]["assignee"] = gitlab_bot_name

    return config


def produce_tasks(
    config: dict[str, Any],
    mcp_clients: dict[str, MCPToolClient],
    task_source: str,
    task_queue: Any,  # InMemoryTaskQueue or RabbitMQTaskQueue
    logger: logging.Logger,
) -> None:
    """タスクを取得してキューに追加する.

    指定されたタスクソース(GitHubまたはGitLab)からタスクを取得し、
    各タスクの準備処理を実行してからキューに追加します。

    Args:
        config: アプリケーション設定辞書
        mcp_clients: MCPクライアントの辞書
        task_source: タスクソース("github" または "gitlab")
        task_queue: タスクキューオブジェクト
        logger: ログ出力用のロガー

    """
    # タスクゲッターのファクトリーメソッドでインスタンス生成
    task_getter = TaskGetter.factory(config, mcp_clients, task_source)

    # タスクリストを取得
    tasks = task_getter.get_task_list()

    # 各タスクの準備処理を実行してキューに追加
    for task in tasks:
        task.prepare()  # ラベル付与などの準備処理
        task_queue.put(task.get_task_key().to_dict())

    logger.info(f"{len(tasks)}件のタスクをキューに追加しました")


def consume_tasks(
    task_queue: Any,  # InMemoryTaskQueue or RabbitMQTaskQueue
    handler: TaskHandler,
    logger: logging.Logger,
    mcp_clients: dict[str, MCPToolClient],
    config: dict[str, Any],
    task_source: str,
) -> None:
    """キューからタスクを取得して処理する.

    タスクキューからタスクを取得し、TaskHandlerを使用して
    各タスクを順次処理します。処理できないタスクはスキップされます。

    Args:
        task_queue: タスクキューオブジェクト
        handler: タスク処理ハンドラー
        logger: ログ出力用のロガー
        mcp_clients: MCPクライアントの辞書
        config: アプリケーション設定辞書
        task_source: タスクソース("github" または "gitlab")

    """
    # タスクゲッターのファクトリーメソッドでインスタンス生成
    task_getter = TaskGetter.factory(config, mcp_clients, task_source)

    while True:
        # キューからタスクキーを取得(5秒でタイムアウト)
        task_key_dict = task_queue.get(timeout=5)
        if task_key_dict is None:
            # タイムアウトした場合はループを終了
            break

        # TaskGetterのfrom_task_keyメソッドでTaskインスタンスを生成
        task = task_getter.from_task_key(task_key_dict)
        if task is None:
            logger.error(f"Unknown or invalid task key: {task_key_dict}")
            continue

        # タスクの状態確認(processing_labelが付与されているかチェック)
        if not hasattr(task, "check") or not task.check():
            logger.info(f"スキップ: processing_labelが付与されていないタスク {task_key_dict}")
            continue

        # タスクの処理実行
        try:
            handler.handle(task)
        except Exception as e:
            logger.exception(f"Task処理中にエラー: {e}")
            # エラーが発生した場合はタスクにコメントを追加
            task.comment(f"処理中にエラーが発生しました: {e}")


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
    args = parser.parse_args()

    # 標準出力・標準エラー出力のライン バッファリング設定
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)

    # ログ設定の初期化
    setup_logger()
    logger = logging.getLogger(__name__)

    # タスクソースの設定取得(デフォルト: "github")
    task_source = os.environ.get("TASK_SOURCE", "github")
    logger.info(f"TASK_SOURCE: {task_source}")

    # 設定ファイルの読み込み
    config_file = "config.yaml"
    config = load_config(config_file)

    # MCPサーバークライアントの初期化
    mcp_clients: dict[str, MCPToolClient] = {}
    functions: list[Any] | None = None
    tools: list[Any] | None = None

    # ファンクションコーリング設定の確認
    function_calling = config.get("llm", {}).get("function_calling", True)
    logger.info(f"function_calling: {function_calling}")

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
            server, config.get("llm", {}).get("function_calling", True),
        )

        # ファンクションコーリングが有効な場合は関数とツールを取得
        if config.get("llm", {}).get("function_calling", True):
            functions.extend(mcp_clients[name].get_function_calling_functions())
            tools.extend(mcp_clients[name].get_function_calling_tools())

    # LLMクライアントの初期化
    llm_client = get_llm_client(config, functions, tools)

    # タスクキューの初期化(RabbitMQまたはインメモリー)
    from queueing import RabbitMQTaskQueue

    if config.get("use_rabbitmq", False):
        # RabbitMQを使用する場合
        task_queue = RabbitMQTaskQueue(config)
    else:
        # インメモリーキューを使用する場合(デフォルト)
        task_queue = InMemoryTaskQueue()

    # タスクハンドラーの初期化
    handler = TaskHandler(llm_client, mcp_clients, config)

    # 実行モードに応じた処理の分岐
    if args.mode == "producer":
        # プロデューサーモード:タスクの取得とキューへの追加のみ
        with FileLock("/tmp/produce_tasks.lock"):
            produce_tasks(config, mcp_clients, task_source, task_queue, logger)
        return
    if args.mode == "consumer":
        # コンシューマーモード:キューからのタスク処理のみ
        consume_tasks(task_queue, handler, logger, mcp_clients, config, task_source)
    else:
        # デフォルトモード:タスク取得→キュー→即時処理の統合実行
        with FileLock("/tmp/produce_tasks.lock"):
            produce_tasks(config, mcp_clients, task_source, task_queue, logger)
        consume_tasks(task_queue, handler, logger, mcp_clients, config, task_source)


if __name__ == "__main__":
    main()
