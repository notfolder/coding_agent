"""LLM呼び出しと応答のrawログを記録するモジュール."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class LLMRawLogger:
    """LLM呼び出しと応答のrawログを記録するクラス."""

    def __init__(self, log_dir: str | Path = "logs") -> None:
        """LLMRawLoggerを初期化する.
        
        Args:
            log_dir: ログファイルを保存するディレクトリ
        """
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # ログファイル名: llm_raw.log.YYYY-MM-DD
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self.log_file = self.log_dir / f"llm_raw.log.{today}"
        
        # ロガーの設定
        self.logger = logging.getLogger("llm_raw")
        self.logger.setLevel(logging.DEBUG)
        
        # ハンドラが既に存在する場合は追加しない
        if not self.logger.handlers:
            handler = logging.FileHandler(self.log_file, encoding="utf-8")
            handler.setLevel(logging.DEBUG)
            
            # シンプルなフォーマット: タイムスタンプとメッセージのみ
            formatter = logging.Formatter("%(asctime)s - %(message)s")
            handler.setFormatter(formatter)
            
            self.logger.addHandler(handler)
            # 親ロガーへの伝播を無効化
            self.logger.propagate = False

    def log_request(
        self,
        provider: str,
        model: str,
        messages: list[dict[str, Any]],
        functions: list[dict[str, Any]] | None = None,
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> None:
        """LLMへのリクエストをログに記録する.
        
        Args:
            provider: プロバイダー名 (openai, ollama, lmstudio等)
            model: モデル名
            messages: メッセージ配列
            functions: 関数定義配列
            tools: ツール定義配列
            **kwargs: その他のリクエストパラメータ
        """
        log_entry = {
            "type": "request",
            "provider": provider,
            "model": model,
            "messages": messages,
        }
        
        if functions:
            log_entry["functions"] = functions
        if tools:
            log_entry["tools"] = tools
        if kwargs:
            log_entry["additional_params"] = kwargs
        
        separator = "=" * 80
        self.logger.debug(f"\n{separator}")
        self.logger.debug("REQUEST")
        self.logger.debug(f"{separator}")
        self.logger.debug(json.dumps(log_entry, indent=2, ensure_ascii=False))

    def log_response(
        self,
        provider: str,
        response: dict[str, Any] | str,
        status_code: int | None = None,
    ) -> None:
        """LLMからのレスポンスをログに記録する.
        
        Args:
            provider: プロバイダー名
            response: レスポンスデータ
            status_code: HTTPステータスコード
        """
        log_entry = {
            "type": "response",
            "provider": provider,
        }
        
        if status_code:
            log_entry["status_code"] = status_code
        
        if isinstance(response, str):
            log_entry["response"] = response
        else:
            log_entry["response"] = response
        
        separator = "=" * 80
        self.logger.debug(f"\n{separator}")
        self.logger.debug("RESPONSE")
        self.logger.debug(f"{separator}")
        self.logger.debug(json.dumps(log_entry, indent=2, ensure_ascii=False))
        self.logger.debug(f"{separator}\n")

    def log_error(
        self,
        provider: str,
        error: Exception | str,
        context: dict[str, Any] | None = None,
    ) -> None:
        """LLM呼び出しのエラーをログに記録する.
        
        Args:
            provider: プロバイダー名
            error: エラー内容
            context: エラーコンテキスト情報
        """
        log_entry = {
            "type": "error",
            "provider": provider,
            "error": str(error),
        }
        
        if context:
            log_entry["context"] = context
        
        separator = "=" * 80
        self.logger.debug(f"\n{separator}")
        self.logger.debug("ERROR")
        self.logger.debug(f"{separator}")
        self.logger.debug(json.dumps(log_entry, indent=2, ensure_ascii=False))
        self.logger.debug(f"{separator}\n")


# グローバルインスタンス
_global_llm_logger: LLMRawLogger | None = None


def get_llm_raw_logger() -> LLMRawLogger:
    """グローバルLLMRawLoggerインスタンスを取得する.
    
    Returns:
        LLMRawLoggerインスタンス
    """
    global _global_llm_logger
    if _global_llm_logger is None:
        _global_llm_logger = LLMRawLogger()
    return _global_llm_logger
