"""MiniMaxDriver for MiniMax-M1 namespaced tool-call tags."""

from __future__ import annotations

import json
from typing import Any

from ayder_cli.parser import content_processor
from ayder_cli.providers.base import ToolCallDef
from ayder_cli.providers.impl.ollama_drivers.base import ChatDriver, DriverMode

_MINIMAX_INSTRUCTION = """

# Tools

Available tools:
<tools>
{tool_schemas}
</tools>

To call a tool, wrap the call in <minimax:tool_call> tags using the
function/parameter format:
<minimax:tool_call>
<function=tool_name>
<parameter=key>value</parameter>
</function>
</minimax:tool_call>
"""


class MiniMaxDriver(ChatDriver):
    name = "minimax"
    mode = DriverMode.IN_CONTENT
    priority = 50
    fallback_driver = "generic_xml"
    supports_families = ("minimax",)

    def render_tools_into_messages(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        if not tools:
            return messages
        schemas = json.dumps(tools, indent=2, ensure_ascii=False)
        instruction = _MINIMAX_INSTRUCTION.format(tool_schemas=schemas)
        output = list(messages)
        system_index = next(
            (i for i, message in enumerate(output) if message.get("role") == "system"),
            None,
        )
        if system_index is not None:
            new_message = dict(output[system_index])
            new_message["content"] = str(new_message.get("content", "")) + instruction
            output[system_index] = new_message
        else:
            output.insert(0, {"role": "system", "content": instruction.lstrip()})
        return output

    def parse_tool_calls(self, content: str, reasoning: str) -> list[ToolCallDef]:
        calls = []
        if content and content_processor.has_tool_calls(content):
            calls = content_processor.parse_tool_calls(content)
        elif reasoning and content_processor.has_tool_calls(reasoning):
            calls = content_processor.parse_tool_calls(reasoning)

        return [
            ToolCallDef(
                id=f"call_{i}",
                name=call.get("name", "unknown"),
                arguments=json.dumps(call.get("arguments", {}), ensure_ascii=False),
            )
            for i, call in enumerate(calls)
            if call.get("name")
        ]
