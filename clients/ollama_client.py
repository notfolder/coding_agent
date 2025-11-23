from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ollama import chat

from .llm_base import LLMClient


class OllamaClient(LLMClient):
    def __init__(
        self,
        config: dict[str, Any],
        message_store: Any = None,
        context_dir: Path | None = None,
    ) -> None:
        self.chat = chat
        self.model = config["model"]
        self.max_token = config.get("max_token", 32768)
        
        # File-based or memory-based mode
        self.message_store = message_store
        self.context_dir = context_dir
        if message_store is None:
            # Legacy mode: use in-memory messages list
            self.messages = []
        else:
            # File-based mode: no in-memory storage
            self.messages = None

    def send_system_prompt(self, prompt: str) -> None:
        if self.message_store:
            self.message_store.add_message("system", prompt)
        else:
            self.messages = [{"role": "system", "content": prompt}]

    def send_user_message(self, message: str) -> None:
        if self.message_store:
            self.message_store.add_message("user", message)
        else:
            self.messages.append({"role": "user", "content": message})
            # トークン数制限: 4文字=1トークンでカウント
            total_chars = sum(len(m["content"]) for m in self.messages)
            while total_chars // 4 > self.max_token:
                self.messages.pop(1)  # 最初のuserから削る
                total_chars = sum(len(m["content"]) for m in self.messages)

    def send_function_result(self, name: str, result: object) -> None:
        msg = "Ollama does not support function calls. Use OpenAI compatible call instead."
        raise NotImplementedError(
            msg,
        )

    def get_response(self) -> str:
        if self.message_store:
            # File-based mode: read messages from current.jsonl
            messages = self._load_messages_from_file()
        else:
            # Legacy mode: use in-memory messages
            messages = self.messages
        
        resp = self.chat(model=self.model, messages=messages)
        reply = resp["message"]["content"]
        
        if self.message_store:
            self.message_store.add_message("assistant", reply)
        else:
            self.messages.append({"role": "assistant", "content": reply})
        
        return reply

    def _load_messages_from_file(self) -> list[dict[str, Any]]:
        """Load messages from current.jsonl file.

        Returns:
            List of messages in Ollama format

        """
        current_file = self.message_store.current_file
        messages = []
        
        if current_file.exists():
            with current_file.open() as f:
                for line in f:
                    msg = json.loads(line.strip())
                    messages.append({
                        "role": msg["role"],
                        "content": msg["content"],
                    })
        
        return messages

