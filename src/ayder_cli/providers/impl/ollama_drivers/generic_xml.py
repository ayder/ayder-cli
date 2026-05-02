"""GenericXMLDriver: universal in-content fallback."""

from __future__ import annotations

import json
from typing import Any

from loguru import logger

from ayder_cli.parser import content_processor
from ayder_cli.providers.base import ToolCallDef
from ayder_cli.providers.impl.ollama_drivers.base import ChatDriver, DriverMode

_XML_INSTRUCTION = """
### TOOL PROTOCOL:
You MUST use the specialized XML format for all tool calls. Failure to use this format will result in a parsing error.
Format:
<tool_call>
<function=tool_name>
<parameter=key1>value1</parameter>
</function>
</tool_call>

Available tools:
{tool_schemas}

The system will execute your tool calls and return the results within `<tool_results>` tags. Do NOT generate `<tool_results>` yourself. Wait for the system to provide the result before taking your next action.

CRITICAL RULES:
1. DO NOT use these XML tags (like <function=> or <parameter=>) in your prose, descriptions, or summaries. Only use them when you intend to call a tool.
2. If you have completed the task and output "Perfect!", you MUST NOT include any tool calls in the same response. "Perfect!" signifies the absolute end of your activity for that task.
3. Use only one tool call at a time unless the task clearly requires parallel execution of independent tools.
"""


class GenericXMLDriver(ChatDriver):
    name = "generic_xml"
    mode = DriverMode.IN_CONTENT
    priority = 950
    fallback_driver = None
    supports_families = ()

    def render_tools_into_messages(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        if not tools:
            return messages

        try:
            tool_schemas = json.dumps(tools, indent=2)
        except Exception as exc:
            logger.warning(f"Failed to serialize tool schemas: {exc}; using str()")
            tool_schemas = str(tools)

        instruction = _XML_INSTRUCTION.format(tool_schemas=tool_schemas)
        output = list(messages)
        system_index = next(
            (i for i, message in enumerate(output) if message.get("role") == "system"),
            None,
        )

        if system_index is not None:
            new_message = dict(output[system_index])
            new_message["content"] = str(new_message.get("content", "")) + "\n" + instruction
            output[system_index] = new_message
        else:
            output.insert(0, {"role": "system", "content": instruction})
        return output

    def parse_tool_calls(self, content: str, reasoning: str) -> list[ToolCallDef]:
        calls = []
        if content and content_processor.has_tool_calls(content):
            calls = content_processor.parse_tool_calls(content)
        elif reasoning and content_processor.has_tool_calls(reasoning):
            calls = content_processor.parse_tool_calls(reasoning)
        elif json_calls := content_processor.parse_json_tool_calls(content):
            calls = json_calls

        return [
            ToolCallDef(
                id=f"call_{i}",
                name=call.get("name", "unknown"),
                arguments=json.dumps(call.get("arguments", {})),
            )
            for i, call in enumerate(calls)
        ]
