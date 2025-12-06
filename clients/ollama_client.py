from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import requests

from .llm_base import LLMClient
from .llm_logger import get_llm_raw_logger
from .token_estimator import estimate_messages_tokens


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
        # 基底クラスの初期化（統計フック初期化）
        super().__init__()
        
        self.endpoint = config.get("endpoint", "http://localhost:11434")
        self.model = config["model"]
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
            name: 実行された関数の名前
            result: 実行結果

        """
        # For function_call mode, send as user message
        output_message = f"output: {result}"
        self.message_store.add_message("user", output_message)

    def add_assistant_message(self, message: str) -> None:
        """アシスタントメッセージをメッセージ履歴に追加する.

        過去コンテキスト引き継ぎ機能で使用します。

        Args:
            message: アシスタントメッセージの内容

        """
        self.message_store.add_message("assistant", message)

    def update_tools(
        self,
        functions: list[dict[str, Any]] | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> None:
        """ツール定義を更新する.

        実行環境ラッパー登録後など、動的にツールを追加する際に使用します。

        Args:
            functions: 新しい関数定義リスト
            tools: 新しいツール定義リスト

        """
        if functions is not None:
            self.functions = functions
        if tools is not None:
            self.tools = tools

    def get_response(self) -> tuple[str, list, int]:
        """Ollama APIから応答を取得する.

        Returns:
            タプル: (応答テキスト, function callsのリスト, トークン数)

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
            # Read request for logging
            with request_path.open("r") as req_file:
                request_data = json.load(req_file)

            # Log request
            self.llm_logger.log_request(
                provider="ollama",
                model=self.model,
                messages=request_data.get("messages", []),
            )

            with request_path.open("rb") as req_file:
                response = requests.post(
                    f"{self.endpoint.rstrip('/')}/api/chat",
                    headers={"Content-Type": "application/json"},
                    data=req_file,
                    timeout=3600,
                )

            response.raise_for_status()
            response_data = response.json()

            # Log response
            self.llm_logger.log_response(
                provider="ollama",
                response=response_data,
                status_code=response.status_code,
            )

            # Parse response - Ollama returns message in different format
            message = response_data.get("message", {})
            reply = message.get("content", "")

            # Add assistant response to message store
            self.message_store.add_message("assistant", reply)
            
            # トークン数を推定
            request_tokens = estimate_messages_tokens(request_data.get("messages", []))
            response_tokens = len(reply) if reply else 0
            total_tokens = request_tokens + response_tokens
            
            # 統計記録フックを呼び出し
            self._invoke_statistics_hook(total_tokens)
            
            return reply, [], total_tokens

        except Exception as e:
            # Log error
            self.llm_logger.log_error(
                provider="ollama",
                error=e,
                context={"model": self.model, "endpoint": self.endpoint},
            )
            raise

        finally:
            # Clean up request.json
            if request_path.exists():
                request_path.unlink()



