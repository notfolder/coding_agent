"""Tool execution history storage.

This module provides a ToolStore class that manages tool execution history
using file-based storage.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ToolStore:
    """File-based tool execution history storage.
    
    Manages tool execution records by writing to tools.jsonl file.
    """

    def __init__(self, context_dir: Path) -> None:
        """Initialize ToolStore.

        Args:
            context_dir: Directory for storing context files

        """
        self.context_dir = context_dir
        self.tools_file = context_dir / "tools.jsonl"

    def add_tool_call(
        self,
        tool_name: str,
        args: dict[str, Any],
        result: Any,
        status: str,
        duration_ms: float,
        error: str | None = None,
    ) -> int:
        """Record a tool execution.

        Args:
            tool_name: Name of the tool
            args: Tool arguments
            result: Tool execution result (if successful)
            status: "success" or "error"
            duration_ms: Execution duration in milliseconds
            error: Error message (if failed)

        Returns:
            Sequence number of the tool call

        """
        # Get next sequence number
        seq = self._get_next_seq()
        
        # Create tool call entry
        timestamp = datetime.now(timezone.utc).isoformat()
        tool_call = {
            "seq": seq,
            "tool": tool_name,
            "args": args,
            "status": status,
            "duration_ms": duration_ms,
            "timestamp": timestamp,
        }
        
        if status == "success":
            tool_call["result"] = result
        else:
            tool_call["error"] = error
        
        # Write to tools.jsonl
        with self.tools_file.open("a") as f:
            f.write(json.dumps(tool_call) + "\n")
        
        return seq

    def count_tool_calls(self) -> int:
        """Count total tool executions.

        Returns:
            Number of tool calls

        """
        if not self.tools_file.exists():
            return 0
        
        with self.tools_file.open() as f:
            return sum(1 for _ in f)

    def _get_next_seq(self) -> int:
        """Get next sequence number.

        Returns:
            Next sequence number (1 if no tool calls exist)

        """
        if not self.tools_file.exists():
            return 1
        
        last_seq = 0
        with self.tools_file.open() as f:
            for line in f:
                call = json.loads(line)
                last_seq = max(last_seq, call.get("seq", 0))
        
        return last_seq + 1
