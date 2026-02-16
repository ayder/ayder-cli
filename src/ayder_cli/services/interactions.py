"""Service interaction protocols for UI decoupling.

Defines the interfaces that services use to communicate presentation events,
keeping service modules free of direct ayder_cli.ui imports.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class InteractionSink(Protocol):
    """Protocol for receiving tool execution notifications.

    Services call these methods to notify about events.
    Adapters implement this to route to CLI or TUI.
    """

    def on_tool_call(self, tool_name: str, args_json: str) -> None:
        """Called when a tool is about to be executed."""
        ...

    def on_tool_result(self, result: str) -> None:
        """Called when a tool execution completes."""
        ...

    def on_tool_skipped(self) -> None:
        """Called when a tool execution is skipped (user declined)."""
        ...

    def on_file_preview(self, file_path: str) -> None:
        """Called to preview file content in verbose mode."""
        ...

    def on_llm_request_debug(
        self,
        messages: list[dict[str, Any]] | list[Any],
        model: str,
        tools: list[dict[str, Any]] | None,
        options: dict[str, Any] | None,
    ) -> None:
        """Called for verbose LLM request debugging."""
        ...


@runtime_checkable
class ConfirmationPolicy(Protocol):
    """Protocol for tool execution confirmation.

    Services call these methods to request user confirmation.
    Adapters implement this to show CLI prompts or TUI modals.
    """

    def confirm_action(self, description: str) -> bool:
        """Request confirmation for a generic action."""
        ...

    def confirm_file_diff(
        self,
        file_path: str,
        new_content: str,
        description: str,
    ) -> bool:
        """Request confirmation with file diff preview."""
        ...
