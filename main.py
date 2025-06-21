import logging
import logging.config
import yaml
import os
import sys
from clients.lm_client import get_llm_client
from clients.mcp_tool_client import MCPToolClient
from handlers.task_getter import TaskGetter
from handlers.task_handler import TaskHandler


def setup_logger():
    logging.config.fileConfig('logging.conf', disable_existing_loggers=False)


def load_config(config_file='config.yaml'):
    with open(config_file, 'r') as f:
        return yaml.safe_load(f)


def main():
    setup_logger()
    logger = logging.getLogger(__name__)
    config_file = sys.argv[1] if len(sys.argv) > 1 else 'config_github.yaml'
    config = load_config(config_file)

    # LLMクライアント初期化
    llm_client = get_llm_client(config)

    # MCPサーバークライアント初期化
    mcp_clients = {}
    for server in config.get('mcp_servers', []):
        name = server['mcp_server_name']
        mcp_clients[name] = MCPToolClient(server)

    # タスク取得
    task_getter = TaskGetter.factory(config, mcp_clients)
    tasks = task_getter.get_task_list()

    # タスク処理
    handler = TaskHandler(llm_client, mcp_clients, config)
    for task in tasks:
        try:
            handler.handle(task)
        except Exception as e:
            logger.exception(f"Task処理中にエラー: {e}")

if __name__ == '__main__':
    main()
