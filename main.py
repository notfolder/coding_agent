import logging
import logging.config
import yaml
import os
import sys
import threading
import time
import argparse
from clients.lm_client import get_llm_client
from clients.mcp_tool_client import MCPToolClient
from handlers.task_getter import TaskGetter
from handlers.task_handler import TaskHandler
from handlers.task_factory import GitHubTaskFactory, GitLabTaskFactory
from handlers.task_key import GitHubIssueTaskKey, GitHubPullRequestTaskKey, GitLabIssueTaskKey, GitLabMergeRequestTaskKey
from queueing import InMemoryTaskQueue
from filelock_util import FileLock
import json


def setup_logger():
    import os
    log_path = os.environ.get('LOGS', 'logs/agent.log')
    loglevel = 'DEBUG' if os.environ.get('DEBUG', '').lower() == 'true' else 'INFO'
    logging.config.fileConfig('logging.conf', defaults={'LOGS': log_path, 'loglevel': loglevel}, disable_existing_loggers=False)


def load_config(config_file='config.yaml'):
    with open(config_file, 'r') as f:
        config = yaml.safe_load(f)
    # function_calling
    function_calling = os.environ.get('FUNCTION_CALLING', 'true').lower() == 'true'
    if 'llm' in config:
        config['llm']['function_calling'] = function_calling
    # provider
    llm_provider = os.environ.get('LLM_PROVIDER')
    if llm_provider:
        if 'llm' in config and 'provider' in config['llm']:
            config['llm']['provider'] = llm_provider
    # lmstudio
    lmstudio_env_url = os.environ.get('LMSTUDIO_BASE_URL')
    if lmstudio_env_url:
        if 'llm' in config and 'lmstudio' in config['llm']:
            config['llm']['lmstudio']['base_url'] = lmstudio_env_url
    lmstudio_env_model = os.environ.get('LMSTUDIO_MODEL')
    if lmstudio_env_model:
        if 'llm' in config and 'lmstudio' in config['llm']:
            config['llm']['lmstudio']['model'] = lmstudio_env_model
    # ollama
    ollama_env_endpoint = os.environ.get('OLLAMA_ENDPOINT')
    if ollama_env_endpoint:
        if 'llm' in config and 'ollama' in config['llm']:
            config['llm']['ollama']['endpoint'] = ollama_env_endpoint
    ollama_env_model = os.environ.get('OLLAMA_MODEL')
    if ollama_env_model:
        if 'llm' in config and 'ollama' in config['llm']:
            config['llm']['ollama']['model'] = ollama_env_model
    # openai
    openai_env_base_url = os.environ.get('OPENAI_BASE_URL')
    if openai_env_base_url:
        if 'llm' in config and 'openai' in config['llm']:
            config['llm']['openai']['base_url'] = openai_env_base_url
    openai_env_model = os.environ.get('OPENAI_MODEL')
    if openai_env_model:
        if 'llm' in config and 'openai' in config['llm']:
            config['llm']['openai']['model'] = openai_env_model
    openai_env_key = os.environ.get('OPENAI_API_KEY')
    if openai_env_key:
        if 'llm' in config and 'openai' in config['llm']:
            config['llm']['openai']['api_key'] = openai_env_key
    # mcp_servers github command
    github_cmd_env = os.environ.get('GITHUB_MCP_COMMAND')
    if github_cmd_env:
        for server in config.get('mcp_servers', []):
            if server.get('mcp_server_name') == 'github':
                # スペース区切りで分割
                server['command'] = github_cmd_env.split()
    # RabbitMQ
    rabbitmq_env = {
        'host': os.environ.get('RABBITMQ_HOST'),
        'port': os.environ.get('RABBITMQ_PORT'),
        'user': os.environ.get('RABBITMQ_USER'),
        'password': os.environ.get('RABBITMQ_PASSWORD'),
        'queue': os.environ.get('RABBITMQ_QUEUE'),
    }
    if 'rabbitmq' not in config:
        config['rabbitmq'] = {}
    for k, v in rabbitmq_env.items():
        if v is not None:
            config['rabbitmq'][k] = v
    # 型変換
    if 'port' in config['rabbitmq'] and config['rabbitmq']['port'] is not None:
        try:
            config['rabbitmq']['port'] = int(config['rabbitmq']['port'])
        except Exception:
            config['rabbitmq']['port'] = 5672
    if 'queue' in config['rabbitmq'] and not config['rabbitmq']['queue']:
        config['rabbitmq']['queue'] = 'mcp_tasks'
    # GITHUB_BOT_NAME, GITLAB_BOT_NAME
    github_bot_name = os.environ.get('GITHUB_BOT_NAME')
    if github_bot_name:
        if 'github' in config and isinstance(config['github'], dict):
            config['github']['assignee'] = github_bot_name
    gitlab_bot_name = os.environ.get('GITLAB_BOT_NAME')
    if gitlab_bot_name:
        if 'gitlab' in config and isinstance(config['gitlab'], dict):
            config['gitlab']['assignee'] = gitlab_bot_name
    return config


def produce_tasks(config, mcp_clients, task_source, task_queue, logger):
    task_getter = TaskGetter.factory(config, mcp_clients, task_source)
    tasks = task_getter.get_task_list()
    for task in tasks:
        task.prepare()
        task_queue.put(task.get_task_key().to_dict())
    logger.info(f"{len(tasks)}件のタスクをキューに追加しました")


def consume_tasks(task_queue, handler, logger, mcp_clients, config, task_source):
    task_getter = TaskGetter.factory(config, mcp_clients, task_source)
    while True:
        task_key_dict = task_queue.get(timeout=5)
        if task_key_dict is None:
            break
        # TaskGetterのfrom_task_keyでTaskインスタンスを生成
        task = task_getter.from_task_key(task_key_dict)
        if task is None:
            logger.error(f"Unknown or invalid task key: {task_key_dict}")
            continue
        if not hasattr(task, 'check') or not task.check():
            logger.info(f"スキップ: processing_labelが付与されていないタスク {task_key_dict}")
            continue
        try:
            handler.handle(task)
        except Exception as e:
            logger.exception(f"Task処理中にエラー: {e}")
            task.comment(f"処理中にエラーが発生しました: {e}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['producer', 'consumer'], help='producer: タスク取得のみ, consumer: キューから実行のみ')
    args = parser.parse_args()

    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)

    setup_logger()
    logger = logging.getLogger(__name__)
    task_source = os.environ.get('TASK_SOURCE', 'github')
    logger.info(f"TASK_SOURCE: {task_source}")
    config_file = 'config.yaml'
    config = load_config(config_file)

    # MCPサーバークライアント初期化
    mcp_clients = {}
    functions = None
    tools = None
    function_calling = config.get('llm', {}).get('function_calling', True)
    logger.info(f"function_calling: {function_calling}")
    if function_calling:
        functions = []
        tools = []
    for server in config.get('mcp_servers', []):
        name = server['mcp_server_name']
        if name in ['github', 'gitlab'] and name != task_source:
            continue  # タスクソースに応じて除外
        mcp_clients[name] = MCPToolClient(server, config.get('llm', {}).get('function_calling', True))
        if config.get('llm', {}).get('function_calling', True):
            functions.extend(mcp_clients[name].get_function_calling_functions())
            tools.extend(mcp_clients[name].get_function_calling_tools())

    # LLMクライアント初期化
    llm_client = get_llm_client(config, functions, tools)

    # タスクキュー初期化
    from queueing import RabbitMQTaskQueue
    if config.get('use_rabbitmq', False):
        task_queue = RabbitMQTaskQueue(config)
    else:
        task_queue = InMemoryTaskQueue()
    handler = TaskHandler(llm_client, mcp_clients, config)

    if args.mode == 'producer':
        with FileLock('/tmp/produce_tasks.lock'):
            produce_tasks(config, mcp_clients, task_source, task_queue, logger)
        return
    elif args.mode == 'consumer':
        consume_tasks(task_queue, handler, logger, mcp_clients, config, task_source)
    else:
        # デフォルト: タスク取得→キュー→即時処理
        with FileLock('/tmp/produce_tasks.lock'):
            produce_tasks(config, mcp_clients, task_source, task_queue, logger)
        consume_tasks(task_queue, handler, logger, mcp_clients, config, task_source)

if __name__ == '__main__':
    main()
