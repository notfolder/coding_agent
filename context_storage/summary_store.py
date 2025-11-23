"""Summary storage for context compression history.

This module provides a SummaryStore class that manages compression/summarization
history using file-based storage.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class SummaryStore:
    """File-based summary storage.
    
    Manages context summarization history by writing to summaries.jsonl file.
    """

    def __init__(self, context_dir: Path) -> None:
        """Initialize SummaryStore.

        Args:
            context_dir: Directory for storing context files

        """
        self.context_dir = context_dir
        self.summaries_file = context_dir / "summaries.jsonl"

    def add_summary(
        self,
        start_seq: int,
        end_seq: int,
        summary_text: str,
        original_tokens: int,
        summary_tokens: int,
    ) -> int:
        """Add a new summary to summaries.jsonl.

        Args:
            start_seq: Starting sequence number of summarized messages
            end_seq: Ending sequence number of summarized messages
            summary_text: Summary text
            original_tokens: Original token count
            summary_tokens: Summary token count

        Returns:
            Summary ID

        """
        # Get next ID
        summary_id = self._get_next_id()
        
        # Calculate compression ratio
        ratio = summary_tokens / original_tokens if original_tokens > 0 else 0.0
        
        # Create summary entry
        timestamp = datetime.now(timezone.utc).isoformat()
        summary = {
            "id": summary_id,
            "start_seq": start_seq,
            "end_seq": end_seq,
            "summary": summary_text,
            "original_tokens": original_tokens,
            "summary_tokens": summary_tokens,
            "ratio": ratio,
            "timestamp": timestamp,
        }
        
        # Write to summaries.jsonl
        with self.summaries_file.open("a") as f:
            f.write(json.dumps(summary) + "\n")
        
        return summary_id

    def get_latest_summary(self) -> dict[str, Any] | None:
        """Get the latest summary.

        Returns:
            Latest summary dict or None if no summaries exist

        """
        if not self.summaries_file.exists():
            return None
        
        latest = None
        with self.summaries_file.open() as f:
            for line in f:
                latest = json.loads(line)
        
        return latest

    def count_summaries(self) -> int:
        """Count total summaries.

        Returns:
            Number of summaries

        """
        if not self.summaries_file.exists():
            return 0
        
        with self.summaries_file.open() as f:
            return sum(1 for _ in f)

    def _get_next_id(self) -> int:
        """Get next summary ID.

        Returns:
            Next summary ID (1 if no summaries exist)

        """
        if not self.summaries_file.exists():
            return 1
        
        last_id = 0
        with self.summaries_file.open() as f:
            for line in f:
                summary = json.loads(line)
                last_id = max(last_id, summary.get("id", 0))
        
        return last_id + 1
