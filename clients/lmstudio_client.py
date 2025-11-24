from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import requests

from .llm_base import LLMClient
from .llm_logger import get_llm_raw_logger


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
        
        # Initialize LLM raw logger
        self.llm_logger = get_llm_raw_logger()

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
        # For function_call mode, send as user message
        output_message = f"output: {result}"
        self.message_store.add_message("user", output_message)

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
            # Read request for logging
            with request_path.open("r") as req_file:
                request_data = json.load(req_file)
            
            # Log request
            self.llm_logger.log_request(
                provider="lmstudio",
                model=self.model,
                messages=request_data.get("messages", []),
            )
            
            with request_path.open("rb") as req_file:
                response = requests.post(
                    f"{self.base_url.rstrip('/')}/chat/completions",
                    headers={"Content-Type": "application/json"},
                    data=req_file,
                    timeout=3600
                )
            
            response.raise_for_status()
            response_data = response.json()
            
            # Log response
            self.llm_logger.log_response(
                provider="lmstudio",
                response=response_data,
                status_code=response.status_code,
            )
            
            # Parse response - OpenAI-compatible format
            reply = ""
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
                        "function_call": func_call,
                    })
                    self.message_store.add_message("assistant", func_call_json)
                    
                    reply += (
                        f"Function call: {func_call.get('name', '')} "
                        f"with arguments {func_call.get('arguments', '')}"
                    )
                elif content:
                    # Only add assistant message if there's actual content
                    self.message_store.add_message("assistant", content)
                    reply += content
            
            return reply
        
        except Exception as e:
            # Log error
            self.llm_logger.log_error(
                provider="lmstudio",
                error=e,
                context={"model": self.model, "base_url": self.base_url},
            )
            raise
            
        finally:
            # Clean up request.json
            if request_path.exists():
                request_path.unlink()



