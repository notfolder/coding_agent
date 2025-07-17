from __future__ import annotations

from typing import Any

import lmstudio as lms
from ollama import chat

from .llm_base import LLMClient


class LMStudioClient(LLMClient):
    """LM Studioを使用するLLMクライアント.

    LM Studio APIを使用してローカルLLMモデルとの対話を実行するクライアント。
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """LM Studioクライアントを初期化する.

        Args:
            config: 設定辞書(base_url, model等を含む)

        """
        lms.configure_default_client(config.get("base_url", "localhost:1234"))
        self.model = lms.llm(config.get("model"))
        self.chat = lms.Chat()
        self.last_response = None

    def send_system_prompt(self, prompt: str) -> None:
        """システムプロンプトをチャットに追加する.

        Args:
            prompt: システムプロンプトの内容

        """
        self.chat.add_system_prompt(prompt)

    def send_user_message(self, message: str) -> None:
        """ユーザーメッセージをチャットに追加する.

        Args:
            message: ユーザーメッセージの内容

        """
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
        result = self.model.respond(self.chat)
        self.chat.add_assistant_response(result)
        return str(result)


class OllamaClient(LLMClient):
    """Ollamaを使用するLLMクライアント.

    Ollama APIを使用してローカルLLMモデルとの対話を実行するクライアント。
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """Ollamaクライアントを初期化する.

        Args:
            config: 設定辞書(model, max_token等を含む)

        """
        self.chat = chat
        self.model = config["model"]
        self.max_token = config.get("max_token", 32768)
        self.messages = []

    def send_system_prompt(self, prompt: str) -> None:
        """システムプロンプトをメッセージ履歴に設定する.

        Args:
            prompt: システムプロンプトの内容

        """
        self.messages = [{"role": "system", "content": prompt}]

    def send_user_message(self, message: str) -> None:
        """ユーザーメッセージをメッセージ履歴に追加する.

        メッセージ履歴が最大トークン数を超えた場合、古いメッセージを削除する。

        Args:
            message: ユーザーメッセージの内容

        """
        self.messages.append({"role": "user", "content": message})
        # トークン数制限
        total_chars = sum(len(m["content"]) for m in self.messages)
        while total_chars // 4 > self.max_token:
            self.messages.pop(1)  # 最初のuserから削る
            total_chars = sum(len(m["content"]) for m in self.messages)

    def get_response(self) -> str:
        """Ollamaからの応答を取得する.

        Returns:
            Ollamaからの応答テキスト

        """
        resp = self.chat(model=self.model, messages=self.messages)
        reply = resp["message"]["content"]
        self.messages.append({"role": "assistant", "content": reply})
        return reply
