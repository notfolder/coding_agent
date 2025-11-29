"""LLMクライアントの基底クラス.

このモジュールは、様々なLLMプロバイダー向けのクライアントクラスで
継承される抽象基底クラスを定義しています。
"""

from abc import ABC, abstractmethod


class LLMClient(ABC):
    """大規模言語モデル(LLM)クライアントの抽象基底クラス.

    このクラスは、OpenAI、Ollama、LM Studio等の様々なLLMプロバイダーに対して
    統一されたインターフェースを提供するための基底クラスです。
    """

    @abstractmethod
    def send_system_prompt(self, prompt: str) -> None:
        """システムプロンプトをLLMに送信する.

        Args:
            prompt: LLMに送信するシステムプロンプト文字列

        """

    @abstractmethod
    def send_user_message(self, message: str) -> None:
        """ユーザーメッセージをLLMに送信する.

        Args:
            message: LLMに送信するユーザーメッセージ文字列

        """

    @abstractmethod
    def get_response(self) -> tuple[str, list, int]:
        """LLMからのレスポンスを取得する.

        Returns:
            タプル: (LLMが生成したレスポンス文字列, function callsのリスト, トークン数)

        """

    def add_assistant_message(self, message: str) -> None:  # noqa: B027
        """アシスタントメッセージをメッセージ履歴に追加する.

        過去コンテキスト引き継ぎ機能で使用します。
        この実装はデフォルトで何もしません。
        サブクラスでmessage_storeがある場合はオーバーライドしてください。

        Args:
            message: アシスタントメッセージの内容

        """
        # デフォルト実装は何もしない
        # message_storeを持つサブクラスでオーバーライド
