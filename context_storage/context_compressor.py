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
        
        # For actual summarization, we would need to use the LLM client
        # However, the current LLM client interface doesn't support
        # one-off requests without affecting the message history.
        # This is a simplified implementation that would need enhancement
        # for production use.
        
        # TODO: Implement proper LLM-based summarization
        # This requires either:
        # 1. Adding a separate summarization method to LLM client
        # 2. Creating a temporary LLM client instance for summarization
        # 3. Using a dedicated summarization service
        
        # For now, return a placeholder to indicate compression occurred
        summary = f"[Context Summary: {len(prompt)} chars of conversation history compressed]"
        
        return summary

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
