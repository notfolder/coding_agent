"""Context compressor for managing context size through summarization.

This module provides a ContextCompressor class that monitors context length
and performs file-based compression/summarization when needed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .message_store import MessageStore
    from .summary_store import SummaryStore


class ContextCompressor:
    """File-based context compression manager.
    
    Monitors context length and performs summarization using LLM
    when threshold is exceeded. All operations are file-based.
    """

    def __init__(
        self,
        message_store: MessageStore,
        summary_store: SummaryStore,
        llm_client: Any,
        config: dict[str, Any],
    ) -> None:
        """Initialize ContextCompressor.

        Args:
            message_store: MessageStore instance
            summary_store: SummaryStore instance
            llm_client: LLM client for generating summaries
            config: Configuration dictionary

        """
        self.message_store = message_store
        self.summary_store = summary_store
        self.llm_client = llm_client
        
        # Get configuration
        llm_config = config.get("llm", {})
        provider = llm_config.get("provider", "openai")
        provider_config = llm_config.get(provider, {})
        
        self.context_length = provider_config.get("context_length", 128000)
        
        context_storage = config.get("context_storage", {})
        self.compression_threshold = context_storage.get("compression_threshold", 0.7)
        self.keep_recent_messages = context_storage.get("keep_recent_messages", 5)
        self.summary_prompt = context_storage.get("summary_prompt", self._default_summary_prompt())
        self.min_messages_to_summarize = 10

    def should_compress(self) -> bool:
        """Check if compression is needed.

        Returns:
            True if current token count exceeds threshold

        """
        current_tokens = self.message_store.get_current_token_count()
        threshold = self.context_length * self.compression_threshold
        return current_tokens > threshold

    def compress(self) -> int:
        """Perform context compression through summarization.

        Returns:
            Summary ID

        """
        context_dir = self.message_store.context_dir
        
        # 1. Extract recent messages to keep unsummarized
        unsummarized_file = context_dir / "unsummarized.jsonl"
        self._extract_recent_messages(unsummarized_file)
        
        # 2. Extract messages to summarize
        to_summarize_file = context_dir / "to_summarize.jsonl"
        original_tokens = self._extract_messages_to_summarize(to_summarize_file)
        
        # 3. Create summary request
        summary_request_file = context_dir / "summary_request.txt"
        self._create_summary_request(to_summarize_file, summary_request_file)
        
        # 4. Get summary from LLM
        summary_text = self._get_summary_from_llm(summary_request_file)
        summary_tokens = len(summary_text) // 4
        
        # 5. Save summary
        summary_id = self.summary_store.add_summary(
            start_seq=1,  # Simplified - in production should track actual seq
            end_seq=self.message_store.count_messages(),
            summary_text=summary_text,
            original_tokens=original_tokens,
            summary_tokens=summary_tokens,
        )
        
        # 6. Recreate current.jsonl with summary and unsummarized messages
        self.message_store.recreate_current_context(
            summary_text,
            summary_tokens,
            unsummarized_file,
        )
        
        # 7. Clean up temporary files
        unsummarized_file.unlink(missing_ok=True)
        to_summarize_file.unlink(missing_ok=True)
        summary_request_file.unlink(missing_ok=True)
        
        return summary_id

    def create_final_summary(self) -> int:
        """タスク完了時に全メッセージから最終要約を生成する.

        compress()とは異なり、全メッセージを要約対象とします。
        current.jsonlは変更せず、summaries.jsonlにのみ要約を追加します。

        Returns:
            Summary ID

        """
        context_dir = self.message_store.context_dir
        
        # 1. 全メッセージを抽出
        all_messages_file = context_dir / "final_summary_input.jsonl"
        original_tokens = self._extract_all_messages(all_messages_file)
        
        if original_tokens == 0:
            # メッセージがない場合はスキップ
            all_messages_file.unlink(missing_ok=True)
            return -1
        
        # 2. 最終要約リクエスト作成
        summary_request_file = context_dir / "final_summary_request.txt"
        self._create_final_summary_request(all_messages_file, summary_request_file)
        
        # 3. LLMから要約取得
        summary_text = self._get_summary_from_llm(summary_request_file)
        summary_tokens = len(summary_text) // 4
        
        # 4. 要約を保存
        summary_id = self.summary_store.add_summary(
            start_seq=1,
            end_seq=self.message_store.count_messages(),
            summary_text=summary_text,
            original_tokens=original_tokens,
            summary_tokens=summary_tokens,
        )
        
        # 5. 一時ファイルを削除
        all_messages_file.unlink(missing_ok=True)
        summary_request_file.unlink(missing_ok=True)
        
        return summary_id

    def _extract_all_messages(self, output_file: Path) -> int:
        """全メッセージをcurrent.jsonlから抽出する（最終要約用）.

        Args:
            output_file: 出力ファイルパス

        Returns:
            総トークン数

        """
        current_file = self.message_store.current_file
        if not current_file.exists():
            return 0
        
        # 全メッセージを読み込み
        messages = []
        total_tokens = 0
        with current_file.open() as f:
            for line in f:
                line = line.strip()
                if line:
                    messages.append(line)
                    msg = json.loads(line)
                    total_tokens += len(msg.get("content", "")) // 4
        
        if not messages:
            return 0
        
        # 出力ファイルに書き込み
        with output_file.open("w") as f:
            for msg in messages:
                f.write(msg + "\n")
        
        return total_tokens

    def _create_final_summary_request(self, messages_file: Path, output_file: Path) -> None:
        """最終要約リクエストを作成する.

        Args:
            messages_file: メッセージファイルパス
            output_file: 出力ファイルパス

        """
        # メッセージを読み込んでフォーマット
        messages_text = ""
        with messages_file.open() as f:
            for line in f:
                msg = json.loads(line.strip())
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                messages_text += f"\n[{role}]: {content}\n"
        
        # 最終要約用のプロンプトを使用
        prompt = self._final_summary_prompt().replace("{messages}", messages_text)
        
        # ファイルに書き込み
        with output_file.open("w") as f:
            f.write(prompt)

    def _final_summary_prompt(self) -> str:
        """最終要約用のプロンプトを取得する.

        Returns:
            最終要約プロンプトテンプレート

        """
        return """あなたはタスク完了時の最終要約を作成するアシスタントです。
以下のタスク実行の全会話履歴を、次回同じIssue/MR/PRが処理される際に引き継ぐための要約にしてください。

要約には以下を含めてください：
1. タスクの目的と要件
2. 実施した変更内容（ファイル名と変更概要）
3. 発生した問題とその解決方法
4. 重要な決定事項や制約条件
5. 残存タスクや今後の課題（あれば）

次回の処理者がこの要約を読んだだけで、前回の処理内容を把握できるように記述してください。
元の会話の20-30%の長さを目標としてください。

=== 全会話履歴 ===
{messages}

=== 指示 ===
上記の会話履歴全体を要約してください。要約のみを出力し、前置きや説明は不要です。"""

    def _extract_recent_messages(self, output_file: Path) -> None:
        """Extract recent N messages from current.jsonl.

        Args:
            output_file: Path to write unsummarized messages

        """
        current_file = self.message_store.current_file
        if not current_file.exists():
            return
        
        # Read all messages
        messages = []
        with current_file.open() as f:
            for line in f:
                messages.append(line.strip())
        
        # Keep last N messages
        recent_messages = messages[-self.keep_recent_messages:]
        
        # Write to output file
        with output_file.open("w") as f:
            for msg in recent_messages:
                f.write(msg + "\n")

    def _extract_messages_to_summarize(self, output_file: Path) -> int:
        """Extract messages to summarize from current.jsonl.

        Args:
            output_file: Path to write messages to summarize

        Returns:
            Total tokens in messages to summarize

        """
        current_file = self.message_store.current_file
        if not current_file.exists():
            return 0
        
        # Read all messages
        messages = []
        with current_file.open() as f:
            for line in f:
                messages.append(line.strip())
        
        # Get messages to summarize (all except recent N)
        if len(messages) <= self.keep_recent_messages:
            return 0
        
        to_summarize = messages[:-self.keep_recent_messages]
        
        # Write to output file
        with output_file.open("w") as f:
            for msg in to_summarize:
                f.write(msg + "\n")
        
        # Calculate tokens
        total_tokens = 0
        for msg_str in to_summarize:
            msg = json.loads(msg_str)
            total_tokens += len(msg.get("content", "")) // 4
        
        return total_tokens

    def _create_summary_request(self, to_summarize_file: Path, output_file: Path) -> None:
        """Create summary request file by combining prompt and messages.

        Args:
            to_summarize_file: Path to messages to summarize
            output_file: Path to write summary request

        """
        # Read messages to summarize
        messages_text = ""
        if to_summarize_file.exists():
            with to_summarize_file.open() as f:
                for line in f:
                    msg = json.loads(line)
                    role = msg.get("role", "")
                    content = msg.get("content", "")
                    messages_text += f"{role}: {content}\n\n"
        
        # Format summary prompt
        prompt = self.summary_prompt.replace("{messages}", messages_text)
        
        # Write to output file
        with output_file.open("w") as f:
            f.write(prompt)

    def _get_summary_from_llm(self, request_file: Path) -> str:
        """Get summary from LLM.

        Args:
            request_file: Path to summary request file

        Returns:
            Summary text

        """
        # Read request
        with request_file.open() as f:
            prompt = f.read()
        
        # LLMクライアントを使用して要約を生成
        try:
            # ユーザーメッセージとして要約リクエストを送信
            self.llm_client.send_user_message(prompt)
            
            # LLMから応答を取得
            response_text, _, _ = self.llm_client.get_response()
            
            summary = response_text.strip()
            
            if not summary:
                # フォールバック: レスポンスが空の場合
                import logging
                logger = logging.getLogger(__name__)
                logger.warning("LLMから空の要約が返されました")
                summary = "[要約生成失敗: LLMから空のレスポンス]"
            
            return summary
        except Exception as e:
            # エラー時のフォールバック
            import logging
            logger = logging.getLogger(__name__)
            logger.exception("LLMによる要約生成に失敗しました: %s", e)
            return f"[要約生成失敗: {e!s}]"

    def _default_summary_prompt(self) -> str:
        """Get default summary prompt.

        Returns:
            Default summary prompt template

        """
        return """あなたは会話履歴を要約するアシスタントです。
以下のメッセージ履歴を簡潔かつ包括的に要約してください。

要約には以下を含めてください：
1. 重要な決定事項
2. 実施したコード変更
3. 発生した問題とその解決
4. 残存タスク

元の30-40%の長さを目標としてください。

=== 要約対象メッセージ ===
{messages}

要約のみを出力してください。"""
