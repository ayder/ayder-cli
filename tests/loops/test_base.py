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
# Iteration counting
# ---------------------------------------------------------------------------


class TestIterationCounting:
    def test_initial_iteration_is_zero(self):
        loop = _make_loop()
        assert loop.iteration == 0

    def test_increment_returns_new_value(self):
        loop = _make_loop()
        assert loop._increment_iteration() == 1
        assert loop._increment_iteration() == 2

    def test_iteration_property_reflects_count(self):
        loop = _make_loop()
        loop._increment_iteration()
        loop._increment_iteration()
        assert loop.iteration == 2

    def test_reset_iterations_public(self):
        loop = _make_loop()
        loop._increment_iteration()
        loop._increment_iteration()
        loop.reset_iterations()
        assert loop.iteration == 0

    def test_reset_iterations_private(self):
        loop = _make_loop()
        loop._iteration = 10
        loop._reset_iterations()
        assert loop._iteration == 0

    def test_direct_attribute_access(self):
        """Tests may set _iteration directly — must remain accessible."""
        loop = _make_loop()
        loop._iteration = 7
        assert loop.iteration == 7


# ---------------------------------------------------------------------------
# Checkpoint trigger
# ---------------------------------------------------------------------------


class TestCheckpointTrigger:
    def test_triggers_at_max(self):
        loop = _make_loop(max_iterations=5)
        loop._iteration = 5
        assert loop._should_trigger_checkpoint() is True

    def test_triggers_above_max(self):
        loop = _make_loop(max_iterations=5)
        loop._iteration = 6
        assert loop._should_trigger_checkpoint() is True

    def test_does_not_trigger_below_max(self):
        loop = _make_loop(max_iterations=5)
        loop._iteration = 4
        assert loop._should_trigger_checkpoint() is False

    def test_zero_max_triggers_immediately(self):
        loop = _make_loop(max_iterations=0)
        loop._iteration = 0
        assert loop._should_trigger_checkpoint() is True


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
        assert cfg.max_iterations == 50
        assert cfg.permissions == set()
        assert cfg.verbose is False
        assert cfg.tool_tags is None

    def test_custom_values(self):
        cfg = LoopConfig(model="gpt-4", max_iterations=10, permissions={"r", "w"})
        assert cfg.model == "gpt-4"
        assert cfg.max_iterations == 10
        assert cfg.permissions == {"r", "w"}
