import logging
import json
import re

class TaskHandler:
    def __init__(self, llm_client, mcp_clients, config):
        self.llm_client = llm_client
        self.mcp_clients = mcp_clients
        self.config = config
        self.logger = logging.getLogger(__name__)

    def handle(self, task):
        task.prepare()
        prompt = task.get_prompt()
        self.logger.info(f"LLMに送信するプロンプト: {prompt}")
        self.llm_client.send_system_prompt(self._make_system_prompt())
        self.llm_client.send_user_message(prompt)
        prev_output = None
        count = 0
        max_count = self.config.get('max_llm_process_num', 1000)
        while count < max_count:
            resp = self.llm_client.get_response()
            self.logger.info(f"LLM応答: {resp}")
            # <think>...</think> の内容をコメントとして投稿し、除去
            think_matches = re.findall(r'<think>(.*?)</think>', resp, flags=re.DOTALL)
            for think_content in think_matches:
                task.comment(think_content.strip())
            resp_clean = re.sub(r'<think>.*?</think>', '', resp, flags=re.DOTALL)
            try:
                data = self._extract_json(resp_clean)
            except Exception as e:
                self.logger.error(f"LLM応答JSONパース失敗: {e}")
                count += 1
                if count >= 5:
                    task.comment("LLM応答エラーでスキップ")
                    break
                continue
            if 'command' in data:
                task.comment(data.get('comment', ''))
                tool = data['command']['tool']
                args = data['command']['args']
                mcp_server, tool_name = tool.split('/', 1)
                output = self.mcp_clients[mcp_server].call_tool(tool_name, args)
                self.llm_client.send_user_message(f"output: {output}")
            if data.get('done'):
                task.comment(data.get('comment', ''))
                task.finish()
                break
            count += 1

    def _make_system_prompt(self):
        # system_prompt.txtを読み込み、mcp_promptをmcp_clientsから取得したsystem_promptで埋め込む
        with open('system_prompt.txt') as f:
            prompt = f.read()
        mcp_prompt = ''
        for name, client in self.mcp_clients.items():
            mcp_prompt += client.system_prompt + '\n'
        return prompt.replace('{mcp_prompt}', mcp_prompt)

    def _extract_json(self, text):
        # テキストから最初のJSONブロックを抽出
        start = text.find('{')
        end = text.rfind('}')
        if start == -1 or end == -1:
            raise ValueError('No JSON found')
        return json.loads(text[start:end+1])
