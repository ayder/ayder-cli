"""Tests for DeepSeekDriver."""

import json

from ayder_cli.providers.impl.ollama_drivers.base import DriverMode
from ayder_cli.providers.impl.ollama_drivers.deepseek import DeepSeekDriver
from ayder_cli.providers.impl.ollama_inspector import ModelInfo


def test_deepseek_metadata():
    assert DeepSeekDriver.name == "deepseek"
    assert DeepSeekDriver.mode is DriverMode.IN_CONTENT
    assert DeepSeekDriver.fallback_driver == "generic_xml"
    assert DeepSeekDriver.priority < 100


def test_deepseek_supports_v2_and_v3_families():
    assert DeepSeekDriver.supports(ModelInfo(family="deepseek2"))
    assert DeepSeekDriver.supports(ModelInfo(family="deepseek3"))
    assert DeepSeekDriver.supports(ModelInfo(family="deepseek-coder"))
    assert not DeepSeekDriver.supports(ModelInfo(family="llama"))


def test_deepseek_render_injects_function_calls_format():
    driver = DeepSeekDriver()
    messages = [{"role": "system", "content": "base"}]
    tools = [
        {
            "type": "function",
            "function": {"name": "read_file", "description": "Read", "parameters": {}},
        }
    ]

    out = driver.render_tools_into_messages(messages, tools)

    system = out[0]["content"]
    assert "<function_calls>" in system
    assert "<invoke" in system
    assert "<parameter" in system
    assert "read_file" in system


def test_deepseek_parse_extracts_invoke_format():
    driver = DeepSeekDriver()
    content = (
        "<function_calls>"
        '<invoke name="read_file">'
        '<parameter name="path">/tmp/x</parameter>'
        "</invoke>"
        "</function_calls>"
    )

    calls = driver.parse_tool_calls(content, "")

    assert len(calls) == 1
    assert calls[0].name == "read_file"
    assert json.loads(calls[0].arguments) == {"path": "/tmp/x"}


def test_deepseek_parse_falls_back_to_reasoning():
    driver = DeepSeekDriver()
    reasoning = (
        "<function_calls>"
        '<invoke name="run_shell">'
        '<parameter name="command">ls</parameter>'
        "</invoke>"
        "</function_calls>"
    )

    calls = driver.parse_tool_calls("", reasoning)

    assert len(calls) == 1
    assert calls[0].name == "run_shell"


def test_deepseek_parse_returns_empty_when_absent():
    driver = DeepSeekDriver()
    assert driver.parse_tool_calls("plain text", "thinking") == []
