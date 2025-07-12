"""
LLMクライアントの基底クラス.

このモジュールは、様々なLLMプロバイダー向けのクライアントクラスで
継承される抽象基底クラスを定義しています。
"""

from abc import ABC, abstractmethod


class LLMClient(ABC):
    """
    大規模言語モデル（LLM）クライアントの抽象基底クラス.
    
    このクラスは、OpenAI、Ollama、LM Studio等の様々なLLMプロバイダーに対して
    統一されたインターフェースを提供するための基底クラスです。
    """

    @abstractmethod
    def send_system_prompt(self, prompt: str) -> None:
        """
        システムプロンプトをLLMに送信する.
        
        Args:
            prompt: LLMに送信するシステムプロンプト文字列
        """
        pass

    @abstractmethod
    def send_user_message(self, message: str) -> None:
        """
        ユーザーメッセージをLLMに送信する.
        
        Args:
            message: LLMに送信するユーザーメッセージ文字列
        """
        pass

    @abstractmethod
    def get_response(self) -> str:
        """
        LLMからのレスポンスを取得する.
        
        Returns:
            LLMが生成したレスポンス文字列
        """
        pass
