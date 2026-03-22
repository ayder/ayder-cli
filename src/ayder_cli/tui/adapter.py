"""TUI adapter implementing InteractionSink for LLM debug events."""

from __future__ import annotations

from typing import Any, Callable

from ayder_cli.services.interactions import InteractionSink


class TUIInteractionSink:
    """Routes on_llm_request_debug events to a TUI callback."""

    def __init__(
        self,
        on_llm_request_debug_cb: Callable[..., None] | None = None,
    ) -> None:
        self._on_llm_request_debug = on_llm_request_debug_cb

    def on_llm_request_debug(
        self,
        messages: list[dict[str, Any]] | list[Any],
        model: str,
        tools: list[dict[str, Any]] | None,
        options: dict[str, Any] | None,
    ) -> None:
        if self._on_llm_request_debug is not None:
            self._on_llm_request_debug(messages, model, tools, options)


# Type guard — verify adapter satisfies protocol at import time
def _check() -> None:
    assert isinstance(TUIInteractionSink(), InteractionSink)
