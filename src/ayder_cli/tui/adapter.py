"""TUI adapters implementing InteractionSink and ConfirmationPolicy.

These adapters live outside services/ and route events to the TUI callback/modal system.
"""

from __future__ import annotations

from typing import Any, Callable

from ayder_cli.services.interactions import ConfirmationPolicy, InteractionSink


class TUIInteractionSink:
    """InteractionSink implementation that routes events to TUI callbacks."""

    def __init__(
        self,
        on_tool_call_cb: Callable[[str, str], None] | None = None,
        on_tool_result_cb: Callable[[str], None] | None = None,
        on_tool_skipped_cb: Callable[[], None] | None = None,
        on_file_preview_cb: Callable[[str], None] | None = None,
        on_llm_request_debug_cb: Callable[..., None] | None = None,
    ) -> None:
        self._on_tool_call = on_tool_call_cb
        self._on_tool_result = on_tool_result_cb
        self._on_tool_skipped = on_tool_skipped_cb
        self._on_file_preview = on_file_preview_cb
        self._on_llm_request_debug = on_llm_request_debug_cb

    def on_tool_call(self, tool_name: str, args_json: str) -> None:
        if self._on_tool_call is not None:
            self._on_tool_call(tool_name, args_json)

    def on_tool_result(self, result: str) -> None:
        if self._on_tool_result is not None:
            self._on_tool_result(result)

    def on_tool_skipped(self) -> None:
        if self._on_tool_skipped is not None:
            self._on_tool_skipped()

    def on_file_preview(self, file_path: str) -> None:
        if self._on_file_preview is not None:
            self._on_file_preview(file_path)

    def on_llm_request_debug(
        self,
        messages: list[dict[str, Any]] | list[Any],
        model: str,
        tools: list[dict[str, Any]] | None,
        options: dict[str, Any] | None,
    ) -> None:
        if self._on_llm_request_debug is not None:
            self._on_llm_request_debug(messages, model, tools, options)


class TUIConfirmationPolicy:
    """ConfirmationPolicy implementation that delegates to TUI callbacks."""

    def __init__(
        self,
        confirm_action_cb: Callable[[str], bool] | None = None,
        confirm_file_diff_cb: Callable[[str, str, str], bool] | None = None,
    ) -> None:
        self._confirm_action = confirm_action_cb
        self._confirm_file_diff = confirm_file_diff_cb

    def confirm_action(self, description: str) -> bool:
        if self._confirm_action is not None:
            return self._confirm_action(description)
        return True

    def confirm_file_diff(
        self,
        file_path: str,
        new_content: str,
        description: str,
    ) -> bool:
        if self._confirm_file_diff is not None:
            return self._confirm_file_diff(file_path, new_content, description)
        return True


# Type guard — verify adapters satisfy protocols at import time
def _check() -> None:
    assert isinstance(TUIInteractionSink(), InteractionSink)
    assert isinstance(TUIConfirmationPolicy(), ConfirmationPolicy)
