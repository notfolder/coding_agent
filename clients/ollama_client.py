from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import requests

from .llm_base import LLMClient


class OllamaClient(LLMClient):
    """Ollama APIを使用するLLMクライアント.
    
    ファイルベースで動作し、メモリに履歴を保持しません。
    """

    def __init__(
        self,
        config: dict[str, Any],
        message_store: Any = None,
        context_dir: Path | None = None,
    ) -> None:
        """Ollamaクライアントを初期化する.

        Args:
            config: 設定辞書(endpoint, model等を含む)
            message_store: MessageStoreインスタンス(必須)
            context_dir: コンテキストディレクトリパス(必須)

        """
        self.endpoint = config.get("endpoint", "http://localhost:11434")
        self.model = config["model"]
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
            name: 実行された関数の名前
            result: 実行結果

        """
        # For function_call mode, send as user message
        output_message = f"output: {result}"
        self.message_store.add_message("user", output_message)

    def get_response(self) -> str:
        """Ollama APIから応答を取得する.

        Returns:
            応答テキスト

        """
        # Create request.json by streaming current.jsonl
        request_path = self.context_dir / "request.json"
        current_file = self.message_store.current_file
        
        with request_path.open("w") as req_file:
            # Write JSON header for Ollama API
            req_file.write('{"model":"')
            req_file.write(self.model)
            req_file.write('","messages":[')
            
            # Stream current.jsonl content (OpenAI format is compatible with Ollama)
            if current_file.exists():
                first = True
                with current_file.open() as current_f:
                    for line in current_f:
                        if not first:
                            req_file.write(',')
                        req_file.write(line.strip())
                        first = False
            
            # Write footer
            req_file.write('],"stream":false}')
        
        # Send request via HTTP POST
        try:
            with request_path.open('rb') as req_file:
                response = requests.post(
                    f"{self.endpoint.rstrip('/')}/api/chat",
                    headers={"Content-Type": "application/json"},
                    data=req_file,
                    timeout=3600
                )
            
            response.raise_for_status()
            response_data = response.json()
            
            # Parse response - Ollama returns message in different format
            message = response_data.get("message", {})
            reply = message.get("content", "")
            
            # Add assistant response to message store
            self.message_store.add_message("assistant", reply)
            
            return reply
            
        finally:
            # Clean up request.json
            if request_path.exists():
                request_path.unlink()


