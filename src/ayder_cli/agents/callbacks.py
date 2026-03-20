"""AgentCallbacks — ChatCallbacks implementation for autonomous agent runs.

Agents auto-approve all tool confirmations. Events are optionally forwarded
to a progress callback (used by AgentPanel in the TUI).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class AgentConfirmResult:
    """Auto-approval result returned by AgentCallbacks.request_confirmation."""
    action: str = "approve"


class AgentCallbacks:
    """ChatCallbacks implementation for agent runs.

    - Auto-approves all tool confirmations
    - Tracks last assistant content (for summary extraction)
    - Cancellation via asyncio.Event
    - Optional progress callback for TUI integration
    """

    def __init__(
        self,
        agent_name: str,
        run_id: int,
        cancel_event: asyncio.Event,
        on_progress: Callable[[int, str, str, Any], None] | None = None,
    ) -> None:
        self.agent_name = agent_name
        self.run_id = run_id
        self._cancel_event = cancel_event
        self._on_progress = on_progress
        self.last_content: str = ""

    def _emit(self, event: str, data: Any = None) -> None:
        if self._on_progress:
            self._on_progress(self.run_id, self.agent_name, event, data)

    # -- ChatCallbacks protocol methods --

    def on_thinking_start(self) -> None:
        self._emit("thinking_start")

    def on_thinking_stop(self) -> None:
        self._emit("thinking_stop")

    def on_assistant_content(self, text: str) -> None:
        self.last_content += text
        self._emit("assistant_content", text)

    def on_thinking_content(self, text: str) -> None:
        self._emit("thinking_content", text)

    def on_token_usage(self, total_tokens: int) -> None:
        self._emit("token_usage", total_tokens)

    def on_tool_start(self, call_id: str, name: str, arguments: dict) -> None:
        self._emit("tool_start", {"call_id": call_id, "name": name, "arguments": arguments})

    def on_tool_complete(self, call_id: str, result: str) -> None:
        self._emit("tool_complete", {"call_id": call_id, "result": result})

    def on_tools_cleanup(self) -> None:
        self._emit("tools_cleanup")

    def on_system_message(self, text: str) -> None:
        self._emit("system_message", text)

    async def request_confirmation(
        self, name: str, arguments: dict
    ) -> AgentConfirmResult:
        """Auto-approve all tool confirmations for autonomous agent runs."""
        logger.debug(f"Agent '{self.agent_name}' auto-approving tool: {name}")
        return AgentConfirmResult(action="approve")

    def is_cancelled(self) -> bool:
        return self._cancel_event.is_set()
