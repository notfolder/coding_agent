# coding: utf-8
import os
import requests

class LMClient:
    def __init__(self, config):
        self.base_url = config['lmstudio']['base_url']
        self.api_key = os.environ.get(config['lmstudio']['api_key_env'])
        self.headers = {'Authorization': f'Bearer {self.api_key}'} if self.api_key else {}
        self.system_prompt_path = os.path.join(os.path.dirname(__file__), '../system_prompt.txt')
        self.first_user_prompt_path = os.path.join(os.path.dirname(__file__), '../first_user_prompt.txt')

    def load_prompt(self, path: str) -> str:
        with open(path, 'r') as f:
            return f.read()

    def chat(self, user_prompt: str, system_prompt: str, previous_output: str = None) -> str:
        prompt = system_prompt + "\n" + user_prompt
        if previous_output:
            prompt += f"\nPrevious output:\n{previous_output}"
        data = {
            "prompt": prompt,
            "max_tokens": 2048,
            "temperature": 0.2
        }
        resp = requests.post(f"{self.base_url}/chat/completions", headers=self.headers, json=data)
        resp.raise_for_status()
        return resp.json()['choices'][0]['message']['content']
