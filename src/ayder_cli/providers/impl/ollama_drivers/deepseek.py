"""DeepSeekDriver for deepseek family — currently dormant.

The matrix routes deepseek family to generic_native because Ollama's native
tool extraction handles it cleanly on current versions (verified empirically
against deepseek-v4-pro:cloud — clean tool_calls, no DSML leak). Injecting our
own <function_calls> XML protocol caused the model to emit <｜DSML｜tool_calls>
wrappers in content that leaked through the display layer.

Kept in-tree as a manual fallback option and as the IN_CONTENT format
reference for any future deepseek variant where native extraction regresses.
To re-enable, add a matrix row routing the specific model/family to "deepseek".
"""

from __future__ import annotations

import json
from typing import Any

from ayder_cli.parser import content_processor
from ayder_cli.providers.base import ToolCallDef
from ayder_cli.providers.impl.ollama_drivers.base import ChatDriver, DriverMode

_DEEPSEEK_INSTRUCTION = """

# Tools

You can call the following tools to help with the user's request.

Available tools:
<tools>
{tool_schemas}
</tools>

To invoke a tool, output a function_calls block:
<function_calls>
<invoke name="tool_name">
<parameter name="key">value</parameter>
</invoke>
</function_calls>

The system will execute the call and return the result. Wait for the result
before continuing.
"""


class DeepSeekDriver(ChatDriver):
    name = "deepseek"
    mode = DriverMode.IN_CONTENT
    priority = 50
    fallback_driver = "generic_xml"
    # Empty: not auto-claimed via supports(). Reachable only via explicit
    # matrix rule or driver-name override. See module docstring.
    supports_families = ()

    def render_tools_into_messages(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        if not tools:
            return messages
        schemas = json.dumps(tools, indent=2, ensure_ascii=False)
        instruction = _DEEPSEEK_INSTRUCTION.format(tool_schemas=schemas)
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
