"""LLMクライアントの基底クラス.

このモジュールは、様々なLLMプロバイダー向けのクライアントクラスで
継承される抽象基底クラスを定義しています。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    pass


class LLMClient(ABC):
    """大規模言語モデル(LLM)クライアントの抽象基底クラス.

    このクラスは、OpenAI、Ollama、LM Studio等の様々なLLMプロバイダーに対して
    統一されたインターフェースを提供するための基底クラスです。
    
    トークン統計記録フック機能:
    - set_statistics_hook()でフック関数を設定
    - get_response()呼び出し後に自動的にフックが実行される
    """

    def __init__(self) -> None:
        """LLMクライアントを初期化する."""
        # トークン統計記録用のフック関数
        self._statistics_hook: Callable[[int, int], None] | None = None

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

    def set_statistics_hook(self, hook: Callable[[int, int], None] | None) -> None:
        """トークン統計記録用のフック関数を設定する.
        
        このフックはget_response()が呼ばれるたびに自動的に実行されます。
        
        Args:
            hook: フック関数。引数は(llm_calls: int, tokens: int)。
                  Noneを設定するとフックを無効化します。
        
        """
        self._statistics_hook = hook

    def _invoke_statistics_hook(self, tokens: int) -> None:
        """統計記録フックを呼び出す.
        
        サブクラスのget_response()実装内で呼び出す必要があります。
        
        Args:
            tokens: 使用したトークン数
        
        """
        if self._statistics_hook is not None:
            try:
                self._statistics_hook(llm_calls=1, tokens=tokens)
            except Exception:
                # フックのエラーは無視（統計記録失敗してもLLM処理は継続）
                import logging
                logger = logging.getLogger(__name__)
                logger.warning("統計記録フックの実行に失敗しました", exc_info=True)

    def add_assistant_message(self, message: str) -> None:  # noqa: B027
        """アシスタントメッセージをメッセージ履歴に追加する.

        過去コンテキスト引き継ぎ機能で使用します。
        この実装はデフォルトで何もしません。
        サブクラスでmessage_storeがある場合はオーバーライドしてください。

        Args:
            message: アシスタントメッセージの内容

        """

    def update_tools(
        self,
        functions: list | None = None,
        tools: list | None = None,
    ) -> None:  # noqa: B027
        """ツール定義を更新する.

        実行環境ラッパー登録後など、動的にツールを追加する際に使用します。
        この実装はデフォルトで何もしません。
        サブクラスでツール管理を行う場合はオーバーライドしてください。

        Args:
            functions: 新しい関数定義リスト
            tools: 新しいツール定義リスト

        """
        # デフォルト実装は何もしない
        # message_storeを持つサブクラスでオーバーライド
