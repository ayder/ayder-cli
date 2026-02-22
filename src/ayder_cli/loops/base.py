"""AgentLoopBase — shared helpers for CLI and TUI agent loops.

Concrete shared logic:
- Iteration counting: _increment_iteration(), _reset_iterations(), iteration property
- Checkpoint trigger detection: _should_trigger_checkpoint() via CheckpointTrigger
- Tool call routing: _route_tool_calls() (XML/JSON/OpenAI format detection)
- Escalation detection: _is_escalation()

Both ChatLoop (CLI) and TuiChatLoop (TUI) extend this class.
Each subclass owns its own run() loop, LLM calls, and UI interactions.
"""

from __future__ import annotations

import json as _json
from typing import Any

from ayder_cli.application.checkpoint_orchestrator import CheckpointTrigger
from ayder_cli.parser import content_processor


class AgentLoopBase:
    """Shared helpers inherited by CLI ChatLoop and TUI TuiChatLoop."""

    def __init__(self, config: Any) -> None:
        self._config = config
        self._iteration: int = 0

    # -- Iteration counting --------------------------------------------------

    @property
    def iteration(self) -> int:
        return self._iteration

    def _increment_iteration(self) -> int:
        """Increment iteration counter and return new value."""
        self._iteration += 1
        return self._iteration

    def _reset_iterations(self) -> None:
        """Reset iteration counter to 0."""
        self._iteration = 0

    def reset_iterations(self) -> None:
        """Public alias for _reset_iterations() — backward-compatible API."""
        self._reset_iterations()

    # -- Checkpoint trigger --------------------------------------------------

    def _should_trigger_checkpoint(self) -> bool:
        """True when iteration count has reached or exceeded max_iterations."""
        trigger = CheckpointTrigger(max_iterations=self._config.max_iterations)
        return trigger.should_trigger(self._iteration)

    # -- Tool call routing ---------------------------------------------------

    def _route_tool_calls(
        self, content: str, native_tool_calls: Any
    ) -> tuple[str, Any, list[dict]]:
        """Route LLM output to the appropriate tool call format.

        Returns:
            (route_type, native_calls, parsed_calls)
            route_type: ``"openai"`` | ``"xml"`` | ``"json"`` | ``"none"``
        """
        if native_tool_calls:
            return "openai", native_tool_calls, []

        if content and content_processor.has_tool_calls(content):
            calls = content_processor.parse_tool_calls(content)
            valid = [c for c in calls if "error" not in c]
            if valid:
                return "xml", None, valid

        json_calls = content_processor.parse_json_tool_calls(content)
        if json_calls:
            return "json", None, json_calls

        return "none", None, []

    # -- Escalation detection ------------------------------------------------

    def _is_escalation(self, result_text: str) -> bool:
        """Detect escalation directive in a tool result payload."""
        try:
            payload = _json.loads(result_text)
        except (ValueError, TypeError):
            return False
        if not isinstance(payload, dict):
            return False
        return (
            payload.get("action") == "escalate"
            or payload.get("action_control") == "escalate"
        )
