from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import openai
import requests

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
        self.api_key = config.get("api_key", "OPENAI_API_KEY")
        self.base_url = config.get("base_url", "https://api.openai.com/")
        self.openai = openai.OpenAI(api_key=self.api_key, base_url=self.base_url, timeout=3600)
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
        # Ensure result is a string
        if isinstance(result, str):
            result_str = result
        else:
            result_str = json.dumps(result)
        
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
            # File-based mode: use request.json file without loading into memory
            return self._get_response_file_based()
        else:
            # Legacy mode: use in-memory messages
            resp = self.openai.chat.completions.create(
                model=self.model,
                messages=self.messages,
                functions=self.functions,
                function_call="auto",
            )
            reply = ""
            functions = []
            for choice in resp.choices:
                content = choice.message.content or ""
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

    def _get_response_file_based(self) -> tuple[str, list[Any]]:
        """Get response using file-based request without loading messages into memory.

        Returns:
            tuple: (応答テキスト, 関数呼び出しリスト)

        """
        # Create request.json by streaming current.jsonl
        request_path = self.context_dir / "request.json"
        current_file = self.message_store.current_file
        
        with request_path.open("w") as req_file:
            # Write JSON header
            req_file.write('{"model":"')
            req_file.write(self.model)
            req_file.write('","messages":[')
            
            # Stream current.jsonl content (already in OpenAI format)
            if current_file.exists():
                first = True
                with current_file.open() as current_f:
                    for line in current_f:
                        if not first:
                            req_file.write(',')
                        req_file.write(line.strip())
                        first = False
            
            # Write functions and footer
            req_file.write(']')
            if self.functions:
                req_file.write(',"functions":')
                req_file.write(json.dumps(self.functions))
                req_file.write(',"function_call":"auto"')
            req_file.write('}')
        
        # Send request via HTTP POST
        try:
            with request_path.open('rb') as req_file:
                response = requests.post(
                    f"{self.base_url.rstrip('/')}/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    data=req_file,
                    timeout=3600
                )
            
            response.raise_for_status()
            response_data = response.json()
            
            # Parse response
            reply = ""
            functions = []
            for choice in response_data.get("choices", []):
                message = choice.get("message", {})
                content = message.get("content") or ""
                
                # Add assistant response to message store
                self.message_store.add_message("assistant", content)
                
                reply += content
                
                # Handle function calls
                if "function_call" in message:
                    func_call = message["function_call"]
                    reply += (
                        f"Function call: {func_call.get('name', '')} "
                        f"with arguments {func_call.get('arguments', '')}"
                    )
                    # Convert to function call object format
                    from types import SimpleNamespace
                    func_obj = SimpleNamespace(
                        name=func_call.get("name", ""),
                        arguments=func_call.get("arguments", "")
                    )
                    functions.append(func_obj)
            
            return reply, functions
            
        finally:
            # Clean up request.json
            if request_path.exists():
                request_path.unlink()

