"""Tests for MiniMaxDriver."""

from ayder_cli.providers.impl.ollama_drivers.base import DriverMode
from ayder_cli.providers.impl.ollama_drivers.minimax import MiniMaxDriver
from ayder_cli.providers.impl.ollama_inspector import ModelInfo


def test_minimax_metadata():
    assert MiniMaxDriver.name == "minimax"
    assert MiniMaxDriver.mode is DriverMode.IN_CONTENT
    assert MiniMaxDriver.fallback_driver == "generic_xml"
    assert MiniMaxDriver.priority < 100


def test_minimax_supports_minimax_family():
    assert MiniMaxDriver.supports(ModelInfo(family="minimax"))
    assert MiniMaxDriver.supports(ModelInfo(family="minimax-m1"))
    assert not MiniMaxDriver.supports(ModelInfo(family="qwen3"))


def test_minimax_render_injects_namespaced_format():
    driver = MiniMaxDriver()
    messages = [{"role": "system", "content": "base"}]
    tools = [{"type": "function", "function": {"name": "read_file"}}]

    out = driver.render_tools_into_messages(messages, tools)

    system = out[0]["content"]
    assert "<minimax:tool_call>" in system
    assert "read_file" in system


def test_minimax_parse_extracts_namespaced_format():
    driver = MiniMaxDriver()
    content = (
        "<minimax:tool_call>"
        "<function=read_file><parameter=path>/tmp</parameter></function>"
        "</minimax:tool_call>"
    )

    calls = driver.parse_tool_calls(content, "")

    assert len(calls) == 1
    assert calls[0].name == "read_file"


def test_minimax_parse_returns_empty_when_absent():
    driver = MiniMaxDriver()
    assert driver.parse_tool_calls("plain text", "") == []
