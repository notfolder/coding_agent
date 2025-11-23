from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import lmstudio as lms

from .llm_base import LLMClient


class LMStudioClient(LLMClient):
    """LM Studioを使用するLLMクライアント.

    LM Studio APIを使用してローカルLLMモデルとの対話を実行するクライアント。
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
            message_store: MessageStoreインスタンス(file-based mode用)
            context_dir: コンテキストディレクトリパス(file-based mode用)

        """
        lms.configure_default_client(config.get("base_url", "localhost:1234"))
        self.model = lms.llm(config.get("model"))
        
        # File-based or memory-based mode
        self.message_store = message_store
        self.context_dir = context_dir
        if message_store is None:
            # Legacy mode: use LMStudio's Chat API
            self.chat = lms.Chat()
        else:
            # File-based mode: no chat object
            self.chat = None
        
        self.last_response = None

    def send_system_prompt(self, prompt: str) -> None:
        """システムプロンプトをチャットに追加する.

        Args:
            prompt: システムプロンプトの内容

        """
        if self.message_store:
            self.message_store.add_message("system", prompt)
        else:
            self.chat.add_system_prompt(prompt)

    def send_user_message(self, message: str) -> None:
        """ユーザーメッセージをチャットに追加する.

        Args:
            message: ユーザーメッセージの内容

        """
        if self.message_store:
            self.message_store.add_message("user", message)
        else:
            self.chat.add_user_message(message)

    def send_function_result(self, name: str, result: object) -> None:
        """関数の実行結果を送信する(LM Studioでは未対応).

        Args:
            name: 関数名
            result: 実行結果

        Raises:
            NotImplementedError: LM Studioは関数呼び出しをサポートしていない

        """
        msg = "LMStudio does not support function calls. Use OpenAI compatible call instead."
        raise NotImplementedError(
            msg,
        )

    def get_response(self) -> str:
        """LLMからの応答を取得する.

        Returns:
            LLMからの応答テキスト

        """
        if self.message_store:
            # File-based mode: need to manually create chat from messages
            chat = lms.Chat()
            messages = self._load_messages_from_file()
            for msg in messages:
                role = msg.get("role")
                content = msg.get("content", "")
                if role == "system":
                    chat.add_system_prompt(content)
                elif role == "user":
                    chat.add_user_message(content)
                elif role == "assistant":
                    chat.add_assistant_response(content)
            
            result = self.model.respond(chat)
            self.message_store.add_message("assistant", str(result))
        else:
            # Legacy mode
            result = self.model.respond(self.chat)
            self.chat.add_assistant_response(result)
        
        return str(result)

    def _load_messages_from_file(self) -> list[dict[str, Any]]:
        """Load messages from current.jsonl file.

        Returns:
            List of messages

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

