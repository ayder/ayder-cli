"""Tests for MiniMaxDriver."""

from ayder_cli.providers.impl.ollama_drivers.base import DriverMode
from ayder_cli.providers.impl.ollama_drivers.minimax import MiniMaxDriver
from ayder_cli.providers.impl.ollama_inspector import ModelInfo


def test_minimax_metadata():
    assert MiniMaxDriver.name == "minimax"
    assert MiniMaxDriver.mode is DriverMode.IN_CONTENT
    assert MiniMaxDriver.fallback_driver == "generic_xml"
    assert MiniMaxDriver.priority < 100


def test_minimax_driver_is_dormant():
    """The minimax family routes to generic_native via the matrix; this
    IN_CONTENT driver self-claims nothing and is reachable only by override."""
    assert MiniMaxDriver.supports_families == ()
    assert not MiniMaxDriver.supports(ModelInfo(family="minimax"))
    assert not MiniMaxDriver.supports(ModelInfo(family="minimax-m1"))


def test_minimax_render_injects_native_invoke_format():
    driver = MiniMaxDriver()
    messages = [{"role": "system", "content": "base"}]
    tools = [{"type": "function", "function": {"name": "read_file"}}]

    out = driver.render_tools_into_messages(messages, tools)

    system = out[0]["content"]
    assert "<minimax:tool_call>" in system
    assert "read_file" in system
    # MiniMax-M2/M3 is natively trained on the invoke/parameter-name format.
    # Instructing it to use anything else produces malformed output.
    assert '<invoke name=' in system
    assert '<parameter name=' in system
    assert "<function=" not in system
    assert "<parameter=" not in system


def test_minimax_parse_extracts_native_invoke_format():
    """The native MiniMax-M2/M3 format must parse with arguments intact."""
    driver = MiniMaxDriver()
    content = (
        "<minimax:tool_call>"
        '<invoke name="write_file">'
        '<parameter name="file_path">daily.html</parameter>'
        "</invoke>"
        "</minimax:tool_call>"
    )

    calls = driver.parse_tool_calls(content, "")

    assert len(calls) == 1
    assert calls[0].name == "write_file"
    assert '"file_path": "daily.html"' in calls[0].arguments


def test_minimax_parse_extracts_legacy_function_format():
    """The legacy M1 <function=> format must still parse (back-compat)."""
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
