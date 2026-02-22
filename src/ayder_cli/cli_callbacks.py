"""CliCallbacks — TuiCallbacks adapter for plain terminal sessions.

Implements the TuiCallbacks protocol so that TuiChatLoop can be driven
from the synchronous CLI without any Textual dependency.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass


@dataclass
class CliConfirmResult:
    """Confirmation result returned by CliCallbacks.request_confirmation()."""

    action: str  # "approve" | "deny"


class CliCallbacks:
    """TuiCallbacks adapter for the CLI — writes to stdout/stderr.

    All write/exec tools are auto-approved, matching the current CLI behaviour
    where ToolExecutor uses AutoApproveConfirmationPolicy.
    """

    def __init__(self, *, verbose: bool = False) -> None:
        self.verbose = verbose
        self._cancelled = False

    # -- lifecycle -----------------------------------------------------------

    def on_thinking_start(self) -> None:
        pass

    def on_thinking_stop(self) -> None:
        pass

    def on_assistant_content(self, text: str) -> None:
        print(text)

    def on_thinking_content(self, text: str) -> None:
        pass

    def on_token_usage(self, total_tokens: int) -> None:
        if self.verbose:
            print(f"[tokens] {total_tokens}", file=sys.stderr)

    def on_iteration_update(self, current: int, maximum: int) -> None:
        if self.verbose:
            print(f"[iteration] {current}/{maximum}", file=sys.stderr)

    # -- tool events ---------------------------------------------------------

    def on_tool_start(self, call_id: str, name: str, arguments: dict) -> None:
        if self.verbose:
            print(f"[tool] {name}", file=sys.stderr, flush=True)

    def on_tool_complete(self, call_id: str, result: str) -> None:
        pass

    def on_tools_cleanup(self) -> None:
        pass

    # -- system / confirmation -----------------------------------------------

    def on_system_message(self, text: str) -> None:
        print(text, file=sys.stderr)

    async def request_confirmation(
        self, name: str, arguments: dict
    ) -> CliConfirmResult:
        """Auto-approve all tool calls (matches current CLI behaviour)."""
        return CliConfirmResult(action="approve")

    def is_cancelled(self) -> bool:
        return self._cancelled
