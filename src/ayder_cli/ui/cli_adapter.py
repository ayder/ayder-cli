"""CLI adapters implementing InteractionSink and ConfirmationPolicy.

These adapters live outside services/ and route events to the Rich CLI UI.
"""

from __future__ import annotations

from typing import Any

from ayder_cli.services.interactions import ConfirmationPolicy, InteractionSink


class CLIInteractionSink:
    """InteractionSink implementation that routes events to the CLI UI."""

    def on_tool_call(self, tool_name: str, args_json: str) -> None:
        from ayder_cli.ui import print_tool_call
        print_tool_call(tool_name, args_json)

    def on_tool_result(self, result: str) -> None:
        from ayder_cli.ui import print_tool_result
        print_tool_result(result)

    def on_tool_skipped(self) -> None:
        from ayder_cli.ui import print_tool_skipped
        print_tool_skipped()

    def on_file_preview(self, file_path: str) -> None:
        from ayder_cli.ui import print_file_content
        print_file_content(file_path)

    def on_llm_request_debug(
        self,
        messages: list[dict[str, Any]] | list[Any],
        model: str,
        tools: list[dict[str, Any]] | None,
        options: dict[str, Any] | None,
    ) -> None:
        from ayder_cli.ui import print_llm_request_debug
        print_llm_request_debug(messages, model, tools, options)


class CLIConfirmationPolicy:
    """ConfirmationPolicy implementation that shows CLI prompts."""

    def confirm_action(self, description: str) -> bool:
        from ayder_cli.ui import confirm_tool_call
        return confirm_tool_call(description)

    def confirm_file_diff(
        self,
        file_path: str,
        new_content: str,
        description: str,
    ) -> bool:
        from ayder_cli.ui import confirm_with_diff
        return confirm_with_diff(file_path, new_content, description)


# Type guard — verify adapters satisfy protocols at import time
def _check() -> None:
    assert isinstance(CLIInteractionSink(), InteractionSink)
    assert isinstance(CLIConfirmationPolicy(), ConfirmationPolicy)
