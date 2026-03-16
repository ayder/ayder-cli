"""Tests for AgentLoopBase — shared loop helpers."""

import json
from unittest.mock import MagicMock

from ayder_cli.loops.base import AgentLoopBase
from ayder_cli.loops.config import LoopConfig


# ---------------------------------------------------------------------------
# Minimal concrete subclass for testing
# ---------------------------------------------------------------------------


class _FakeLoop(AgentLoopBase):
    """Minimal concrete subclass — inherits all base helpers."""
    pass


def _make_loop(max_iterations: int = 50) -> _FakeLoop:
    config = MagicMock()
    config.max_iterations = max_iterations
    return _FakeLoop(config)


# ---------------------------------------------------------------------------
# Class hierarchy
# ---------------------------------------------------------------------------


class TestClassHierarchy:
    def test_tui_chat_loop_extends_agent_loop_base(self):
        from ayder_cli.tui.chat_loop import TuiChatLoop
        assert issubclass(TuiChatLoop, AgentLoopBase)

    def test_loops_package_exports(self):
        from ayder_cli.loops import AgentLoopBase, LoopConfig
        assert AgentLoopBase is not None
        assert LoopConfig is not None


# ---------------------------------------------------------------------------
# Tool call routing
# ---------------------------------------------------------------------------


class TestRouteToolCalls:
    def test_openai_native_takes_priority(self):
        loop = _make_loop()
        native = MagicMock()
        route, nc, pc = loop._route_tool_calls("any content", native)
        assert route == "openai"
        assert nc is native
        assert pc == []

    def test_xml_detected_when_no_native(self):
        loop = _make_loop()
        xml = '<function=read_file><parameter=file_path>test.py</parameter></function>'
        route, nc, pc = loop._route_tool_calls(xml, None)
        assert route == "xml"
        assert nc is None
        assert len(pc) == 1
        assert pc[0]["name"] == "read_file"

    def test_json_fallback(self):
        loop = _make_loop()
        jcalls = json.dumps([
            {"id": "1", "function": {"name": "list_files", "arguments": '{"directory":"."}'}, "type": "function"}
        ])
        route, nc, pc = loop._route_tool_calls(jcalls, None)
        assert route == "json"
        assert nc is None
        assert pc[0]["name"] == "list_files"

    def test_none_when_no_calls(self):
        loop = _make_loop()
        route, nc, pc = loop._route_tool_calls("plain text response", None)
        assert route == "none"
        assert nc is None
        assert pc == []

    def test_empty_content_returns_none(self):
        loop = _make_loop()
        route, nc, pc = loop._route_tool_calls("", None)
        assert route == "none"


# ---------------------------------------------------------------------------
# Escalation detection
# ---------------------------------------------------------------------------


class TestEscalationDetection:
    def test_detects_action_escalate(self):
        loop = _make_loop()
        assert loop._is_escalation('{"action": "escalate"}') is True

    def test_detects_action_control_escalate(self):
        loop = _make_loop()
        assert loop._is_escalation('{"action_control": "escalate"}') is True

    def test_non_escalation_payload(self):
        loop = _make_loop()
        assert loop._is_escalation('{"action": "hold"}') is False

    def test_invalid_json(self):
        loop = _make_loop()
        assert loop._is_escalation("not json") is False

    def test_empty_payload(self):
        loop = _make_loop()
        assert loop._is_escalation("{}") is False


# ---------------------------------------------------------------------------
# LoopConfig
# ---------------------------------------------------------------------------


class TestLoopConfig:
    def test_defaults(self):
        cfg = LoopConfig()
        assert cfg.model == "qwen3-coder:latest"
        assert cfg.num_ctx == 65536
        assert cfg.permissions == set()
        assert cfg.verbose is False
        assert cfg.tool_tags is None

    def test_custom_values(self):
        cfg = LoopConfig(model="gpt-4", permissions={"r", "w"})
        assert cfg.model == "gpt-4"
        assert cfg.permissions == {"r", "w"}
