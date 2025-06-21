from .llm_base import LLMClient
import os

class OpenAIClient(LLMClient):
    def __init__(self, config):
        import openai
        self.openai = openai
        self.model = config['model']
        self.max_token = config.get('max_token', 32768)
        self.messages = []
        api_key_env = config.get('api_key_env', 'OPENAI_API_KEY')
        self.openai.api_key = os.environ.get(api_key_env)

    def send_system_prompt(self, prompt: str) -> None:
        self.messages = [{"role": "system", "content": prompt}]

    def send_user_message(self, message: str) -> None:
        self.messages.append({"role": "user", "content": message})
        total_chars = sum(len(m['content']) for m in self.messages)
        while total_chars // 4 > self.max_token:
            self.messages.pop(1)
            total_chars = sum(len(m['content']) for m in self.messages)

    def get_response(self) -> str:
        resp = self.openai.ChatCompletion.create(model=self.model, messages=self.messages)
        reply = resp.choices[0].message.content
        self.messages.append({"role": "assistant", "content": reply})
        return reply
