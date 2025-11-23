from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import requests

from .llm_base import LLMClient


class OpenAIClient(LLMClient):
    """OpenAI APIを使用するLLMクライアント.

    OpenAI ChatCompletion APIを使用してテキスト生成や関数呼び出しを実行するクライアント。
    ファイルベースで動作し、メモリに履歴を保持しません。
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
            message_store: MessageStoreインスタンス(必須)
            context_dir: コンテキストディレクトリパス(必須)

        """
        self.api_key = config.get("api_key", "OPENAI_API_KEY")
        self.base_url = config.get("base_url", "https://api.openai.com/")
        self.model = config["model"]
        self.functions = functions
        self.tools = tools
        self.message_store = message_store
        self.context_dir = context_dir

    def send_system_prompt(self, prompt: str) -> None:
        """システムプロンプトをメッセージ履歴に追加する.

        Args:
            prompt: システムプロンプトの内容

        """
        self.message_store.add_message("system", prompt)

    def send_user_message(self, message: str) -> None:
        """ユーザーメッセージをメッセージ履歴に追加する.

        Args:
            message: ユーザーメッセージの内容

        """
        self.message_store.add_message("user", message)

    def send_function_result(self, name: str, result: object) -> None:
        """関数の実行結果をメッセージ履歴に追加する.

        Args:
            name: 実行された関数の名前
            result: 関数の実行結果

        """
        # For function_call mode (not tool_calls), send as user message
        output_message = f"output: {result}"
        self.message_store.add_message("user", output_message)

    def get_response(self) -> str:
        """OpenAI APIから応答を取得する.

        Returns:
            LLMからの応答テキスト

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
                    f"{self.base_url.rstrip('/')}/chat/completions",
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
                
                # Handle function calls
                if "function_call" in message:
                    func_call = message["function_call"]
                    
                    # Add function call info to assistant message
                    func_call_json = json.dumps({
                        "role": "assistant",
                        "content": None,
                        "function_call": func_call
                    })
                    self.message_store.add_message("assistant", func_call_json)
                    
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
                elif content:
                    # Only add assistant message if there's actual content
                    self.message_store.add_message("assistant", content)
                    reply += content
            
            return reply
            
        finally:
            # Clean up request.json
            if request_path.exists():
                request_path.unlink()


