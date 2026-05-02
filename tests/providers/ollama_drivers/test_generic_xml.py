"""Tests for GenericXMLDriver."""

import json

from ayder_cli.providers.impl.ollama_drivers.base import DriverMode
from ayder_cli.providers.impl.ollama_drivers.generic_xml import GenericXMLDriver


def test_generic_xml_metadata():
    assert GenericXMLDriver.name == "generic_xml"
    assert GenericXMLDriver.mode is DriverMode.IN_CONTENT
    assert GenericXMLDriver.fallback_driver is None
    assert GenericXMLDriver.priority >= 900


def test_render_injects_instruction_into_existing_system_message():
    driver = GenericXMLDriver()
    messages = [
        {"role": "system", "content": "base system"},
        {"role": "user", "content": "hi"},
    ]
    tools = [{"type": "function", "function": {"name": "read_file"}}]

    out = driver.render_tools_into_messages(messages, tools)

    assert out[0]["role"] == "system"
    assert "base system" in out[0]["content"]
    assert "TOOL PROTOCOL:" in out[0]["content"]
    assert "read_file" in out[0]["content"]
    assert out[1] == messages[1]


def test_render_creates_system_message_when_missing():
    driver = GenericXMLDriver()
    messages = [{"role": "user", "content": "hi"}]
    tools = [{"type": "function", "function": {"name": "read_file"}}]

    out = driver.render_tools_into_messages(messages, tools)

    assert out[0]["role"] == "system"
    assert "TOOL PROTOCOL:" in out[0]["content"]


def test_render_with_no_tools_is_passthrough():
    driver = GenericXMLDriver()
    messages = [{"role": "system", "content": "x"}]
    assert driver.render_tools_into_messages(messages, []) == messages


def test_parse_extracts_function_xml_format():
    driver = GenericXMLDriver()
    content = (
        "<function=read_file>"
        "<parameter=path>/tmp/x.txt</parameter>"
        "</function>"
    )

    calls = driver.parse_tool_calls(content, "")

    assert len(calls) == 1
    assert calls[0].name == "read_file"
    assert json.loads(calls[0].arguments) == {"path": "/tmp/x.txt"}


def test_parse_returns_empty_when_no_tool_call_present():
    driver = GenericXMLDriver()
    assert driver.parse_tool_calls("just narration", "just thinking") == []


def test_parse_falls_back_to_reasoning_payload():
    driver = GenericXMLDriver()
    reasoning = "<function=run_shell><parameter=command>ls</parameter></function>"

    calls = driver.parse_tool_calls("", reasoning)

    assert len(calls) == 1
    assert calls[0].name == "run_shell"
