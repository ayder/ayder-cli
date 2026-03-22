"""Service interaction protocols for UI decoupling.

Defines the interface that LLM providers use to emit debug events,
keeping providers free of direct UI imports.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class InteractionSink(Protocol):
    """Protocol for receiving LLM provider debug notifications."""

    def on_llm_request_debug(
        self,
        messages: list[dict[str, Any]] | list[Any],
        model: str,
        tools: list[dict[str, Any]] | None,
        options: dict[str, Any] | None,
    ) -> None:
        """Called for verbose LLM request debugging."""
        ...
