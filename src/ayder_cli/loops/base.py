"""AgentLoopBase — shared helpers for CLI and TUI agent loops.

Concrete shared logic:
- Tool call routing: _route_tool_calls() (XML/JSON/OpenAI format detection)
- Escalation detection: _is_escalation()

ChatLoop (in loops/chat_loop.py) extends this class.
"""

from __future__ import annotations

import json as _json
from typing import Any

from ayder_cli.parser import content_processor


class AgentLoopBase:
    """Shared helpers inherited by ChatLoop."""

    def __init__(self, config: Any) -> None:
        self._config = config

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
            if calls:
                return "xml", None, calls

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
