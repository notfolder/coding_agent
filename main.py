# coding: utf-8
import logging
import logging.config
import os
import time
from clients.mcp_client import MCPClient
from clients.lm_client import LMClient
from handlers.issue_handler import IssueHandler

def setup_logger():
    import yaml
    config_path = os.path.join(os.path.dirname(__file__), 'logger_config.yaml')
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        logging.config.dictConfig(config)
    else:
        logging.basicConfig(level=logging.INFO)


def load_config():
    import yaml
    config_path = os.path.join(os.path.dirname(__file__), 'mcp_config.yaml')
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def main():
    setup_logger()
    logger = logging.getLogger(__name__)
    config = load_config()
    mcp_client = MCPClient(config)
    lm_client = LMClient(config)
    issue_handler = IssueHandler(mcp_client, lm_client, config)

    interval = config.get('scheduling', {}).get('interval', 300)
    while True:
        try:
            issue_handler.process_issues()
        except Exception as e:
            logger.exception(f"Error in main loop: {e}")
        time.sleep(interval)

if __name__ == "__main__":
    main()
