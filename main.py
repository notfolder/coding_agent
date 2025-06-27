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
    return config


def main():
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
        mcp_clients[name] = MCPToolClient(server, config.get('llm', {}).get('function_calling', True))
        if config.get('llm', {}).get('function_calling', True):
            functions.extend(mcp_clients[name].get_function_calling_functions())
            tools.extend(mcp_clients[name].get_function_calling_tools())
        # logging.debug(f"{name}: {mcp_clients[name].system_prompt}")


    # LLMクライアント初期化
    llm_client = get_llm_client(config, functions, tools)

    # タスク取得
    task_getter = TaskGetter.factory(config, mcp_clients, task_source)
    tasks = task_getter.get_task_list()

    # タスク処理
    handler = TaskHandler(llm_client, mcp_clients, config)

    for task in tasks:
        try:
            handler.handle(task)
        except Exception as e:
            logger.exception(f"Task処理中にエラー: {e}")
            task.comment(f"処理中にエラーが発生しました: {e}")

if __name__ == '__main__':
    main()
