# coding: utf-8
import logging
import json
import re
from clients.mcp_client import MCPClient
from clients.lm_client import LMClient

class IssueHandler:
    def __init__(self, mcp_client: MCPClient, lm_client: LMClient, config):
        self.mcp_client = mcp_client
        self.lm_client = lm_client
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.bot_label = config['github']['bot_label']
        self.system_prompt = self.lm_client.load_prompt('system_prompt.txt')
        self.first_user_prompt = self.lm_client.load_prompt('first_user_prompt.txt')

    def process_issues(self):
        issues = self.mcp_client.get_issues(self.bot_label)
        for issue in issues:
            self.process_single_issue(issue)

    def process_single_issue(self, issue):
        logger = self.logger
        user_prompt = self.first_user_prompt.format(
            issue_number=issue['number'],
            title=issue['title'],
            body=issue['body'],
            owner=self.config['github']['owner'],
            repo=self.config['github']['repo']
        )
        previous_output = None
        retry = 0
        max_retry = 5
        done = False
        while not done and retry < max_retry:
            try:
                response = self.lm_client.chat(user_prompt, self.system_prompt, previous_output)
                json_obj = self._extract_json(response)
                if not json_obj:
                    raise ValueError('No JSON found in LLM response')
                if 'command' in json_obj:
                    tool = json_obj['command']['tool']
                    args = json_obj['command']['args']
                    tool_output = self.mcp_client.call_tool(tool, args)
                    previous_output = json.dumps({'output': tool_output}, ensure_ascii=False)
                    self.mcp_client.add_issue_comment(issue['number'], f"```
{json.dumps(json_obj, ensure_ascii=False, indent=2)}
```")
                elif json_obj.get('done'):
                    self.mcp_client.add_issue_comment(issue['number'], f"```
{json.dumps(json_obj, ensure_ascii=False, indent=2)}
```")
                    self.mcp_client.update_issue(issue['number'], self.bot_label)
                    done = True
                else:
                    self.mcp_client.add_issue_comment(issue['number'], f"```
{json.dumps(json_obj, ensure_ascii=False, indent=2)}
```")
                    previous_output = None
            except Exception as e:
                logger.exception(f"Error processing issue #{issue['number']}: {e}")
                retry += 1
                if retry >= max_retry:
                    self.mcp_client.add_issue_comment(issue['number'], f"エージェントエラー: {e}")
                    self.mcp_client.update_issue(issue['number'], self.bot_label)

    def _extract_json(self, text):
        try:
            match = re.search(r'\{[\s\S]*\}', text)
            if match:
                return json.loads(match.group(0))
        except Exception:
            pass
        return None
