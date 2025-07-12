from .llm_base import LLMClient


class OllamaClient(LLMClient):
    def __init__(self, config) -> None:
        from ollama import chat

        self.chat = chat
        self.model = config["model"]
        self.max_token = config.get("max_token", 32768)
        self.messages = []

    def send_system_prompt(self, prompt: str) -> None:
        self.messages = [{"role": "system", "content": prompt}]

    def send_user_message(self, message: str) -> None:
        self.messages.append({"role": "user", "content": message})
        # トークン数制限: 4文字=1トークンでカウント
        total_chars = sum(len(m["content"]) for m in self.messages)
        while total_chars // 4 > self.max_token:
            self.messages.pop(1)  # 最初のuserから削る
            total_chars = sum(len(m["content"]) for m in self.messages)

    def send_function_result(self, name: str, result) -> None:
        msg = "Ollama does not support function calls. Use OpenAI compatible call instead."
        raise NotImplementedError(
            msg,
        )

    def get_response(self) -> str:
        resp = self.chat(model=self.model, messages=self.messages)
        reply = resp["message"]["content"]
        self.messages.append({"role": "assistant", "content": reply})
        return reply
