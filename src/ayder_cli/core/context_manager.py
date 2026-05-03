"""ContextManager Protocol and shared utilities.

This module defines the abstract contract for all context managers.
Concrete implementations live in separate modules:
  - DefaultContextManager  (default_context_manager.py)
  - OllamaContextManager   (ollama_context_manager.py, Task 5)
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass
class ContextStats:
    """Base statistics about current context usage."""

    total_tokens: int = 0
    available_tokens: int = 0
    utilization_percent: float = 0.0
    message_count: int = 0
    compaction_count: int = 0
    messages_compacted: int = 0


@runtime_checkable
class ContextManagerProtocol(Protocol):
    """Closed contract for all context managers.

    New providers add new implementations without modifying this protocol.
    """

    def freeze_system_prompt(
        self, system_content: str, tool_schemas: list[dict]
    ) -> None:
        """Lock the system prefix. Called once at session start."""
        ...

    def prepare_messages(
        self,
        messages: list[dict],
        max_history: int = 0,
    ) -> list[dict]:
        """Return a trimmed message list that fits the context budget."""
        ...

    def update_from_response(self, usage: dict[str, int]) -> None:
        """Ingest provider-reported metrics after each LLM response."""
        ...

    def get_stats(self) -> ContextStats:
        """Return current context utilization metrics."""
        ...

    def should_compact(self) -> bool:
        """Whether compaction/trimming should be triggered."""
        ...


def truncate_tool_result(content: str, max_chars: int = 8192) -> str:
    """Truncate a tool result at insertion time. Shared by all implementations.

    ``max_chars=0`` is the explicit "exempt" sentinel — used by tools whose
    output is already bounded by their own pagination (e.g. ``read_file``).
    Generic head+tail truncation would silently corrupt such payloads.
    """
    if max_chars == 0:
        return content
    if not content or len(content) <= max_chars:
        return content

    if content.strip().startswith(("{", "[")):
        try:
            data = json.loads(content)
            summary = _summarize_structure(data)
            return (
                f"[Tool result compressed - {len(content)} chars]\n"
                f"Summary: {summary}"
            )
        except json.JSONDecodeError:
            pass

    head_len = int(max_chars * 0.4)
    tail_len = int(max_chars * 0.1)
    head = content[:head_len]
    tail = content[-tail_len:] if tail_len > 0 else ""
    removed = len(content) - head_len - tail_len

    return (
        f"{head}\n\n"
        f"--- [TRUNCATED {removed} CHARS FOR CONTEXT EFFICIENCY] ---\n\n"
        f"{tail}"
    )


def _summarize_structure(data: Any, max_depth: int = 2) -> str:
    """Summarize JSON structure for compressed tool results."""
    if max_depth <= 0:
        return "..."
    if isinstance(data, dict):
        if not data:
            return "{}"
        items = []
        for k, v in list(data.items())[:5]:
            items.append(f"{k}: {_summarize_structure(v, max_depth - 1)}")
        if len(data) > 5:
            items.append(f"... ({len(data) - 5} more keys)")
        return "{" + ", ".join(items) + "}"
    if isinstance(data, list):
        if not data:
            return "[]"
        item_summary = _summarize_structure(data[0], max_depth - 1)
        return f"[{len(data)} items, e.g.: {item_summary}]"
    if isinstance(data, str):
        if len(data) > 50:
            return f'"{data[:50]}..."'
        return f'"{data}"'
    return str(data)


# ---------------------------------------------------------------------------
# Backward compatibility
# ---------------------------------------------------------------------------
# ChatLoop (loops/chat_loop.py) still does:
#   from ayder_cli.core.context_manager import ContextManager
#   self.context_manager = ContextManager(config=config, model=config.model)
#
# Until Task 8 wires DI, we re-export DefaultContextManager under the old name.
# The Protocol above is accessible as ContextManagerProtocol.
# After Task 8, this alias is deleted and ContextManager becomes the Protocol.
from ayder_cli.core.default_context_manager import (  # noqa: E402
    DefaultContextManager as ContextManager,
)

__all__ = [
    "ContextStats",
    "ContextManagerProtocol",
    "ContextManager",
    "truncate_tool_result",
]
