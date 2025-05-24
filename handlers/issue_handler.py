import logging
import os
from typing import Dict, Any
from clients.mcp_client import GitHubMCPClient
from clients.lm_client import LMClient

class IssueHandler:
    def __init__(self, mcp_client: GitHubMCPClient, lm_client: LMClient, config: Dict[str, Any]):
        self.mcp_client = mcp_client
        self.lm_client = lm_client
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.owner = config['github']['owner']
        self.repo = config['github']['repo']
        self.bot_label = config['github']['bot_label']
        self.system_prompt_path = os.path.join(os.path.dirname(__file__), '../system_prompt.txt')
        self.user_prompt_path = os.path.join(os.path.dirname(__file__), '../first_user_prompt.txt')

    def process_all_issues(self):
        issues = self.mcp_client.get_issues(self.bot_label)
        for issue in issues:
            try:
                self.process_issue(issue)
            except Exception as e:
                self.logger.exception(f"Failed to process issue #{issue['number']}: {e}")

    def process_issue(self, issue):
        with open(self.system_prompt_path) as f:
            system_prompt = f.read()
        with open(self.user_prompt_path) as f:
            user_prompt_template = f.read()
        user_prompt = user_prompt_template.format(
            issue_number=issue['number'],
            title=issue['title'],
            body=issue['body'],
            owner=self.owner,
            repo=self.repo
        )
        previous_output = None
        for retry in range(5):
            try:
                while True:
                    response = self.lm_client.chat(system_prompt, user_prompt, previous_output)
                    json_part = self._extract_json(response)
                    if not json_part:
                        raise ValueError("No JSON found in LLM response")
                    self.mcp_client.add_issue_comment(issue['number'], response)
                    if 'done' in json_part and json_part['done']:
                        self.mcp_client.update_issue(issue['number'], self.bot_label)
                        break
                    if 'command' in json_part:
                        tool = json_part['command']['tool']
                        args = json_part['command']['args']
                        output = self.mcp_client.call_tool(str(issue['number']), tool, args)
                        previous_output = str(output)
                    else:
                        break
                break
            except Exception as e:
                self.logger.warning(f"Retry {retry+1}/5 for issue #{issue['number']}: {e}")
                if retry == 4:
                    self.mcp_client.add_issue_comment(issue['number'], f"Error: {e}")
                    self.mcp_client.update_issue(issue['number'], self.bot_label)

    def _extract_json(self, text):
        import json, re
        matches = re.findall(r'\{[\s\S]*\}', text)
        for m in matches:
            try:
                return json.loads(m)
            except Exception:
                continue
        return None
