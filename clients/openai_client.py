import json
from .llm_base import LLMClient
import os

class OpenAIClient(LLMClient):
    def __init__(self, config, functions=None, tools=None):
        import openai
        api_key = config.get('api_key', 'OPENAI_API_KEY')
        base_url = config.get('base_url', 'https://api.openai.com/')
        self.openai = openai.OpenAI(api_key=api_key, base_url=base_url, timeout=3600)
        self.model = config['model']
        self.max_token = config.get('max_token', 40960)
        self.messages = []
        self.functions = functions
        self.tools = tools

    def send_system_prompt(self, prompt: str) -> None:
        self.messages.append({"role": "system", "content": prompt})

    def send_user_message(self, message: str) -> None:
        self.messages.append({"role": "user", "content": message})
        total_chars = sum(len(m['content']) for m in self.messages)
        while total_chars // 4 > self.max_token:
            self.messages.pop(1)
            total_chars = sum(len(m['content']) for m in self.messages)

    def send_function_result(self, name: str, result) -> None:
        self.messages.append({"role": "tool", "name": name, "content": json.dumps(result)})
        total_chars = sum(len(m['content']) for m in self.messages)
        while total_chars // 4 > self.max_token:
            self.messages.pop(1)
            total_chars = sum(len(m['content']) for m in self.messages)

    def get_response(self) -> tuple[str, list[any]]:
        resp = self.openai.chat.completions.create(
            model=self.model,
            messages=self.messages,
            # tools=self.tools,
            functions=self.functions,
            function_call="auto"
        )
        reply = ""
        functions = []
        for choice in resp.choices:
            self.messages.append({"role": choice.message.role, "content": choice.message.content})
            reply += choice.message.content
            if choice.message.function_call is not None:
                reply += f"Function call: {choice.message.function_call.name} with arguments {choice.message.function_call.arguments}"
                functions.append(choice.message.function_call)
        return reply, functions
