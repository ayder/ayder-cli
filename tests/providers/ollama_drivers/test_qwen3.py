"""Tests for Qwen3Driver."""

import json

from ayder_cli.providers.impl.ollama_drivers.base import DriverMode
from ayder_cli.providers.impl.ollama_drivers.qwen3 import Qwen3Driver
from ayder_cli.providers.impl.ollama_inspector import ModelInfo


def test_qwen3_metadata():
    assert Qwen3Driver.name == "qwen3"
    assert Qwen3Driver.mode is DriverMode.IN_CONTENT
    assert Qwen3Driver.fallback_driver == "generic_xml"
    assert Qwen3Driver.priority < 100
    assert "qwen3" in Qwen3Driver.supports_families


def test_qwen3_supports_via_default_family_match():
    assert Qwen3Driver.supports(ModelInfo(family="qwen3"))
    assert Qwen3Driver.supports(ModelInfo(family="qwen2"))
    assert not Qwen3Driver.supports(ModelInfo(family="llama"))


def test_qwen3_render_injects_qwen_native_format():
    driver = Qwen3Driver()
    messages = [
        {"role": "system", "content": "base"},
        {"role": "user", "content": "hi"},
    ]
    tools = [
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Reads a file",
                "parameters": {"type": "object"},
            },
        }
    ]

    out = driver.render_tools_into_messages(messages, tools)

    system = out[0]["content"]
    assert "<tools>" in system
    assert "</tools>" in system
    assert "<tool_call>" in system
    assert "</tool_call>" in system
    assert "read_file" in system
    assert out[1] == messages[1]


def test_qwen3_render_with_no_tools_is_passthrough():
    driver = Qwen3Driver()
    messages = [{"role": "system", "content": "x"}]
    assert driver.render_tools_into_messages(messages, []) == messages


def test_qwen3_parse_extracts_qwen_json_format():
    driver = Qwen3Driver()
    content = (
        "<tool_call>\n"
        '{"name": "read_file", "arguments": {"path": "/tmp/x.txt"}}\n'
        "</tool_call>"
    )

    calls = driver.parse_tool_calls(content, "")

    assert len(calls) == 1
    assert calls[0].name == "read_file"
    assert json.loads(calls[0].arguments) == {"path": "/tmp/x.txt"}


def test_qwen3_parse_handles_string_arguments():
    driver = Qwen3Driver()
    content = (
        "<tool_call>"
        '{"name": "shell", "arguments": "{\\"cmd\\": \\"ls\\"}"}'
        "</tool_call>"
    )

    calls = driver.parse_tool_calls(content, "")

    assert len(calls) == 1
    assert json.loads(calls[0].arguments) == {"cmd": "ls"}


def test_qwen3_parse_extracts_multiple_calls():
    driver = Qwen3Driver()
    content = (
        '<tool_call>{"name": "a", "arguments": {}}</tool_call>'
        "mid prose "
        '<tool_call>{"name": "b", "arguments": {"k": "v"}}</tool_call>'
    )

    calls = driver.parse_tool_calls(content, "")

    assert [call.name for call in calls] == ["a", "b"]


def test_qwen3_parse_falls_back_to_function_xml_format():
    driver = Qwen3Driver()
    content = "<function=read_file><parameter=path>/tmp</parameter></function>"

    calls = driver.parse_tool_calls(content, "")

    assert len(calls) == 1
    assert calls[0].name == "read_file"


def test_qwen3_parse_returns_empty_for_pure_narration():
    driver = Qwen3Driver()
    assert driver.parse_tool_calls("I'll read the file.", "thinking...") == []


def test_qwen3_parse_skips_malformed_json():
    driver = Qwen3Driver()
    content = "<tool_call>{not valid json}</tool_call>"
    assert driver.parse_tool_calls(content, "") == []
