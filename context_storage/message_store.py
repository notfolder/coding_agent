"""Message storage for file-based context management.

This module provides a MessageStore class that manages message history
using files instead of in-memory storage to reduce memory usage.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class MessageStore:
    """File-based message storage without memory caching.
    
    Manages message history by writing to messages.jsonl and current.jsonl files.
    All operations are file-based to minimize memory usage.
    """

    def __init__(self, context_dir: Path, config: dict[str, Any]) -> None:
        """Initialize MessageStore.

        Args:
            context_dir: Directory for storing context files
            config: Configuration dictionary containing context_length

        """
        self.context_dir = context_dir
        self.messages_file = context_dir / "messages.jsonl"
        self.current_file = context_dir / "current.jsonl"
        self.context_length = config.get("llm", {}).get(config.get("llm", {}).get("provider", "openai"), {}).get("context_length", 128000)

    def add_message(self, role: str, content: str, tool_name: str | None = None) -> int:
        """Add a new message to both messages.jsonl and current.jsonl.

        Args:
            role: Message role (system/user/assistant/tool)
            content: Message content
            tool_name: Tool name (only for role="tool")

        Returns:
            Sequence number of the added message

        """
        # Get next sequence number
        seq = self._get_next_seq()
        
        # Calculate tokens (4 chars = 1 token approximation)
        tokens = len(content) // 4
        
        # Create full message entry for messages.jsonl
        timestamp = datetime.now(timezone.utc).isoformat()
        full_message = {
            "seq": seq,
            "role": role,
            "content": content,
            "timestamp": timestamp,
            "tokens": tokens,
        }
        if tool_name:
            full_message["tool_name"] = tool_name
        
        # Write to messages.jsonl
        with self.messages_file.open("a") as f:
            f.write(json.dumps(full_message) + "\n")
        
        # Create OpenAI format message for current.jsonl
        current_message = {"role": role, "content": content}
        if tool_name:
            current_message["tool_name"] = tool_name
        
        # Write to current.jsonl
        with self.current_file.open("a") as f:
            f.write(json.dumps(current_message) + "\n")
        
        return seq

    def get_current_context_file(self, unsummarized_file_path: Path | None = None) -> Path:
        """Get path to current context file.

        If unsummarized_file_path is provided, creates a combined file.

        Args:
            unsummarized_file_path: Optional path to unsummarized messages file

        Returns:
            Path to current.jsonl or combined file

        """
        if unsummarized_file_path is None:
            return self.current_file
        
        # Create combined file
        combined_file = self.context_dir / "current_combined.jsonl"
        with combined_file.open("w") as out_f:
            # Copy current.jsonl
            if self.current_file.exists():
                with self.current_file.open() as in_f:
                    out_f.write(in_f.read())
            
            # Append unsummarized messages
            if unsummarized_file_path.exists():
                with unsummarized_file_path.open() as in_f:
                    out_f.write(in_f.read())
        
        return combined_file

    def get_current_token_count(self) -> int:
        """Calculate total tokens in current.jsonl by reading from messages.jsonl.

        Returns:
            Total token count

        """
        if not self.current_file.exists():
            return 0
        
        # Count lines in current.jsonl to get message count
        with self.current_file.open() as f:
            current_count = sum(1 for _ in f)
        
        # Read last N messages from messages.jsonl and sum tokens
        if not self.messages_file.exists():
            return 0
        
        total_tokens = 0
        messages_list = []
        with self.messages_file.open() as f:
            for line in f:
                messages_list.append(json.loads(line))
        
        # Get the last current_count messages
        for msg in messages_list[-current_count:]:
            total_tokens += msg.get("tokens", 0)
        
        return total_tokens

    def count_messages(self) -> int:
        """Count total messages in messages.jsonl.

        Returns:
            Number of messages

        """
        if not self.messages_file.exists():
            return 0
        
        with self.messages_file.open() as f:
            return sum(1 for _ in f)

    def recreate_current_context(
        self,
        summary_text: str,
        summary_tokens: int,
        unsummarized_file_path: Path,
    ) -> None:
        """Recreate current.jsonl with summary and unsummarized messages.

        Args:
            summary_text: Summary text to add as first message
            summary_tokens: Token count of summary
            unsummarized_file_path: Path to unsummarized messages file

        """
        # Delete old current.jsonl
        if self.current_file.exists():
            self.current_file.unlink()
        
        # Write summary as first message (OpenAI format)
        with self.current_file.open("w") as f:
            summary_msg = {"role": "assistant", "content": summary_text}
            f.write(json.dumps(summary_msg) + "\n")
        
        # Append unsummarized messages (already in OpenAI format)
        if unsummarized_file_path.exists():
            with unsummarized_file_path.open() as in_f, self.current_file.open("a") as out_f:
                out_f.write(in_f.read())
        
        # Also add summary to messages.jsonl for complete history
        seq = self._get_next_seq()
        timestamp = datetime.now(timezone.utc).isoformat()
        full_summary = {
            "seq": seq,
            "role": "assistant",
            "content": summary_text,
            "timestamp": timestamp,
            "tokens": summary_tokens,
        }
        with self.messages_file.open("a") as f:
            f.write(json.dumps(full_summary) + "\n")

    def _get_next_seq(self) -> int:
        """Get next sequence number.

        Returns:
            Next sequence number (1 if no messages exist)

        """
        if not self.messages_file.exists():
            return 1
        
        last_seq = 0
        with self.messages_file.open() as f:
            for line in f:
                msg = json.loads(line)
                last_seq = max(last_seq, msg.get("seq", 0))
        
        return last_seq + 1
