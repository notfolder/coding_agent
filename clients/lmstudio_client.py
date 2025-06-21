from .llm_base import LLMClient

class LMStudioClient(LLMClient):
    def __init__(self, config):
        import lmstudio as lms
        self.model = lms.llm(config.get('model'))
        self.chat = lms.Chat()
        self.last_response = None

    def send_system_prompt(self, prompt: str) -> None:
        self.chat.add_system_prompt(prompt)
        # self.chat = self.model.Chat(prompt)

    def send_user_message(self, message: str) -> None:
        self.chat.add_user_message(message)

    def get_response(self) -> str:
        result = self.model.respond(self.chat)
        self.chat.add_assistant_response(result)
        # self.chat.add_assistant_message(result)
        return str(result)

class OllamaClient(LLMClient):
    def __init__(self, config):
        from ollama import chat
        self.chat = chat
        self.model = config['model']
        self.max_token = config.get('max_token', 32768)
        self.messages = []

    def send_system_prompt(self, prompt: str) -> None:
        self.messages = [{"role": "system", "content": prompt}]

    def send_user_message(self, message: str) -> None:
        self.messages.append({"role": "user", "content": message})
        # トークン数制限
        total_chars = sum(len(m['content']) for m in self.messages)
        while total_chars // 4 > self.max_token:
            self.messages.pop(1)  # 最初のuserから削る
            total_chars = sum(len(m['content']) for m in self.messages)

    def get_response(self) -> str:
        resp = self.chat(model=self.model, messages=self.messages)
        reply = resp['message']['content']
        self.messages.append({"role": "assistant", "content": reply})
        return reply
