"""Qwen3Driver: qwen2/qwen3 trained tool-call format."""

from __future__ import annotations

import json
import re
from typing import Any

from ayder_cli.parser import content_processor
from ayder_cli.providers.base import ToolCallDef
from ayder_cli.providers.impl.ollama_drivers.base import ChatDriver, DriverMode

_QWEN3_INSTRUCTION = """

# Tools

You may call one or more functions to assist with the user query.

You are provided with function signatures within <tools></tools> XML tags:
<tools>
{tool_schemas}
</tools>

For each function call, return a json object with function name and arguments
within <tool_call></tool_call> XML tags:
<tool_call>
{{"name": <function-name>, "arguments": <args-json-object>}}
</tool_call>
"""


class Qwen3Driver(ChatDriver):
    name = "qwen3"
    mode = DriverMode.IN_CONTENT
    priority = 50
    fallback_driver = "generic_xml"
    supports_families = ("qwen2", "qwen3")

    _RE_TOOL_CALL_JSON = re.compile(
        r"<(?:\w+:)?tool_call>\s*(\{.*?\})\s*</(?:\w+:)?tool_call>",
        re.DOTALL,
    )

    def render_tools_into_messages(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        if not tools:
            return messages
        schemas = "\n".join(json.dumps(tool, ensure_ascii=False) for tool in tools)
        instruction = _QWEN3_INSTRUCTION.format(tool_schemas=schemas)
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
        calls = self._parse_json_in_tool_call(content)
        if not calls:
            calls = self._parse_json_in_tool_call(reasoning)

        if not calls and content and content_processor.has_tool_calls(content):
            calls = self._parse_generic_xml(content)
        if not calls and reasoning and content_processor.has_tool_calls(reasoning):
            calls = self._parse_generic_xml(reasoning)

        return [
            ToolCallDef(
                id=f"call_{i}",
                name=call["name"],
                arguments=json.dumps(call["arguments"], ensure_ascii=False),
            )
            for i, call in enumerate(calls)
        ]

    def _parse_json_in_tool_call(self, text: str) -> list[dict[str, Any]]:
        if not text:
            return []
        results: list[dict[str, Any]] = []
        for match in self._RE_TOOL_CALL_JSON.finditer(text):
            try:
                obj = json.loads(match.group(1))
            except (json.JSONDecodeError, ValueError):
                continue
            if not isinstance(obj, dict):
                continue
            name = obj.get("name")
            if not name:
                continue
            arguments = obj.get("arguments", {})
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except (json.JSONDecodeError, ValueError):
                    arguments = {}
            if not isinstance(arguments, dict):
                arguments = {}
            results.append({"name": name, "arguments": arguments})
        return results

    def _parse_generic_xml(self, text: str) -> list[dict[str, Any]]:
        return [
            {
                "name": call.get("name", "unknown"),
                "arguments": call.get("arguments", {}),
            }
            for call in content_processor.parse_tool_calls(text)
            if call.get("name")
        ]
