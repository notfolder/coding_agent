import logging
import logging.config
import os
from typing import List, TypedDict, Optional
import yaml
from clients.mcp_client import GitHubMCPClient
from clients.lm_client import LMClient
from handlers.issue_handler import IssueHandler

CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'mcp_config.yaml')
LOG_CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'logging.conf')

# ログディレクトリ作成
os.makedirs('logs', exist_ok=True)
logging.config.fileConfig(LOG_CONFIG_PATH)
logger = logging.getLogger(__name__)

def load_config(path: str):
    with open(path, 'r') as f:
        return yaml.safe_load(f)

def main():
    config = load_config(CONFIG_PATH)
    mcp_client = GitHubMCPClient(config['mcp'], config['github'])
    lm_client = LMClient(config['lmstudio'])
    issue_handler = IssueHandler(mcp_client, lm_client, config)
    try:
        issue_handler.process_all_issues()
    except Exception as e:
        logger.exception(f"Agent failed: {e}")

if __name__ == "__main__":
    main()
