from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import openai

from .llm_base import LLMClient


class OpenAIClient(LLMClient):
    """OpenAI APIを使用するLLMクライアント.

    OpenAI ChatCompletion APIを使用してテキスト生成や関数呼び出しを実行するクライアント。
    """

    def __init__(
        self,
        config: dict[str, Any],
        functions: list[dict[str, Any]] | None = None,
        tools: list[dict[str, Any]] | None = None,
        message_store: Any = None,
        context_dir: Path | None = None,
    ) -> None:
        """OpenAIクライアントを初期化する.

        Args:
            config: 設定辞書(api_key, base_url, model等を含む)
            functions: 利用可能な関数の定義リスト
            tools: 利用可能なツールの定義リスト
            message_store: MessageStoreインスタンス(file-based mode用)
            context_dir: コンテキストディレクトリパス(file-based mode用)

        """
        api_key = config.get("api_key", "OPENAI_API_KEY")
        base_url = config.get("base_url", "https://api.openai.com/")
        self.openai = openai.OpenAI(api_key=api_key, base_url=base_url, timeout=3600)
        self.model = config["model"]
        self.max_token = config.get("max_token", 40960)
        self.functions = functions
        self.tools = tools
        
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
        """システムプロンプトをメッセージ履歴に追加する.

        Args:
            prompt: システムプロンプトの内容

        """
        if self.message_store:
            self.message_store.add_message("system", prompt)
        else:
            self.messages.append({"role": "system", "content": prompt})

    def send_user_message(self, message: str) -> None:
        """ユーザーメッセージをメッセージ履歴に追加する.

        メッセージ履歴が最大トークン数を超えた場合、古いメッセージを削除する。

        Args:
            message: ユーザーメッセージの内容

        """
        if self.message_store:
            self.message_store.add_message("user", message)
        else:
            self.messages.append({"role": "user", "content": message})
            total_chars = sum(len(m["content"]) for m in self.messages)
            while total_chars // 4 > self.max_token:
                self.messages.pop(1)
                total_chars = sum(len(m["content"]) for m in self.messages)

    def send_function_result(self, name: str, result: object) -> None:
        """関数の実行結果をメッセージ履歴に追加する.

        Args:
            name: 実行された関数の名前
            result: 関数の実行結果

        """
        result_str = json.dumps(result) if not isinstance(result, str) else result
        
        if self.message_store:
            self.message_store.add_message("tool", result_str, tool_name=name)
        else:
            self.messages.append({"role": "tool", "name": name, "content": result_str})
            total_chars = sum(len(m["content"]) for m in self.messages)
            while total_chars // 4 > self.max_token:
                self.messages.pop(1)
                total_chars = sum(len(m["content"]) for m in self.messages)

    def get_response(self) -> tuple[str, list[Any]]:
        """OpenAI APIから応答を取得する.

        Returns:
            tuple: (応答テキスト, 関数呼び出しリスト)

        """
        if self.message_store:
            # File-based mode: read messages from current.jsonl
            messages = self._load_messages_from_file()
        else:
            # Legacy mode: use in-memory messages
            messages = self.messages
        
        resp = self.openai.chat.completions.create(
            model=self.model,
            messages=messages,
            functions=self.functions,
            function_call="auto",
        )
        reply = ""
        functions = []
        for choice in resp.choices:
            content = choice.message.content or ""
            
            if self.message_store:
                self.message_store.add_message("assistant", content)
            else:
                self.messages.append({"role": choice.message.role, "content": content})
            
            reply += content
            if choice.message.function_call is not None:
                func_call = choice.message.function_call
                reply += (
                    f"Function call: {func_call.name} "
                    f"with arguments {func_call.arguments}"
                )
                functions.append(choice.message.function_call)
        return reply, functions

    def _load_messages_from_file(self) -> list[dict[str, Any]]:
        """Load messages from current.jsonl file.

        Returns:
            List of messages in OpenAI format

        """
        current_file = self.message_store.current_file
        messages = []
        
        if current_file.exists():
            with current_file.open() as f:
                for line in f:
                    msg = json.loads(line.strip())
                    # Convert to OpenAI API format
                    if msg.get("tool_name"):
                        messages.append({
                            "role": msg["role"],
                            "name": msg["tool_name"],
                            "content": msg["content"],
                        })
                    else:
                        messages.append({
                            "role": msg["role"],
                            "content": msg["content"],
                        })
        
        return messages

