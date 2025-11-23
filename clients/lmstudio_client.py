from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import requests

from .llm_base import LLMClient


class LMStudioClient(LLMClient):
    """LM Studioを使用するLLMクライアント.

    LM Studio APIを使用してローカルLLMモデルとの対話を実行するクライアント。
    OpenAI互換APIを使用し、ファイルベースで動作します。
    """

    def __init__(
        self,
        config: dict[str, Any],
        message_store: Any = None,
        context_dir: Path | None = None,
    ) -> None:
        """LM Studioクライアントを初期化する.

        Args:
            config: 設定辞書(base_url, model等を含む)
            message_store: MessageStoreインスタンス(必須)
            context_dir: コンテキストディレクトリパス(必須)

        """
        base_url = config.get("base_url", "localhost:1234")
        # Add http:// if not present
        if not base_url.startswith(("http://", "https://")):
            base_url = f"http://{base_url}"
        self.base_url = base_url
        self.model = config.get("model", "local-model")
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
        """関数の実行結果を送信する.

        Args:
            name: 関数名
            result: 実行結果

        """
        # LM Studio supports tool calls in OpenAI-compatible format
        if isinstance(result, str):
            result_str = result
        else:
            result_str = json.dumps(result)
        
        self.message_store.add_message("tool", result_str, tool_name=name)

    def get_response(self) -> str:
        """LLMからの応答を取得する.

        Returns:
            LLMからの応答テキスト

        """
        # Create request.json by streaming current.jsonl
        request_path = self.context_dir / "request.json"
        current_file = self.message_store.current_file
        
        with request_path.open("w") as req_file:
            # Write JSON header - LM Studio uses OpenAI-compatible API
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
            
            # Write footer
            req_file.write(']}')
        
        # Send request via HTTP POST to OpenAI-compatible endpoint
        try:
            with request_path.open('rb') as req_file:
                response = requests.post(
                    f"{self.base_url.rstrip('/')}/v1/chat/completions",
                    headers={"Content-Type": "application/json"},
                    data=req_file,
                    timeout=3600
                )
            
            response.raise_for_status()
            response_data = response.json()
            
            # Parse response - OpenAI-compatible format
            reply = ""
            for choice in response_data.get("choices", []):
                message = choice.get("message", {})
                content = message.get("content") or ""
                reply += content
            
            # Add assistant response to message store
            if reply:
                self.message_store.add_message("assistant", reply)
            
            return reply
            
        finally:
            # Clean up request.json
            if request_path.exists():
                request_path.unlink()


