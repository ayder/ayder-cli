"""Tool definitions declare which calls may run concurrently (audit P0-2).

A batch runs in emission order; only consecutive calls that are parallel-safe
and auto-approved share a parallel segment. Unknown and unclassified tools are
barriers. No network (environment: local-faked).
"""

from __future__ import annotations

import pytest

from ayder_cli.agents.tool import AGENT_TOOL_DEFINITION
from ayder_cli.loops.chat_loop import _plan_tool_segments
from ayder_cli.providers.base import _FunctionCall, _ToolCall
from ayder_cli.tools.definition import (
    TOOL_DEFINITIONS_BY_NAME,
    ToolDefinition,
    is_parallel_safe,
    parallel_safe_when,
)


def _c(call_id):
    return _ToolCall(id=call_id, type="function",
                     function=_FunctionCall(name="read_file", arguments="{}"))


@pytest.mark.parametrize("name,args,expected", [
    ("read_file", {"file_path": "a"}, True),
    ("file_explorer", {}, True),
    ("search_codebase", {"pattern": "x"}, True),
    ("get_project_structure", {}, True),
    ("skill", {"action": "load", "name": "x"}, True),
    ("task", {"action": "list"}, True), ("task", {"action": "show"}, True),
    ("task", {"action": "status"}, True), ("task", {"action": "update"}, False),
    ("task", {"action": "create"}, False),
    ("context", {"action": "stats"}, True), ("context", {"action": "list"}, True),
    ("context", {"action": "load"}, True), ("context", {"action": "save"}, False),
    ("context", {"action": "clear"}, False),
    ("note", {"action": "read"}, True), ("note", {"action": "list"}, True),
    ("note", {"action": "update"}, False),
    ("background_process", {"action": "logs"}, True),
    ("background_process", {"action": "info"}, True),
    ("background_process", {"action": "start"}, False),
    ("background_process", {"action": "stop"}, False),
    ("fetch_web", {"url": "https://x"}, True),
    ("fetch_web", {"url": "https://x", "method": "HEAD"}, True),
    ("fetch_web", {"url": "https://x", "method": "POST"}, False),
    ("file_editor", {"file_path": "a", "operation": "write", "content": ""}, False),
    ("bash", {"command": "ls"}, False),
    ("manage_environment_vars", {"mode": "validate"}, False),
    ("no_such_tool", {}, False),
])
def test_builtin_classification(name, args, expected):
    """New interface."""
    assert is_parallel_safe(name, args) is expected


@pytest.mark.parametrize("action,expected", [
    ("list", True), ("status", True), ("read_result", True), ("call", False)])
def test_agent_classification(monkeypatch, action, expected):
    """New interface: agent call dispatches a run, so it is a barrier."""
    monkeypatch.setitem(TOOL_DEFINITIONS_BY_NAME, "agent", AGENT_TOOL_DEFINITION)
    assert is_parallel_safe("agent", {"action": action}) is expected


def test_default_definition_is_not_parallel_safe(monkeypatch):
    """New interface: a plugin definition that never set the flag is a barrier."""
    td = ToolDefinition(name="plugin_x", description="x", parameters={"type": "object"})
    monkeypatch.setitem(TOOL_DEFINITIONS_BY_NAME, "plugin_x", td)
    assert is_parallel_safe("plugin_x", {}) is False


@pytest.mark.parametrize("args", [{}, {"method": "get"}, {"method": ["GET"]}])
def test_predicate_mismatch_is_barrier(args):
    """New interface: values match exactly; anything else is a barrier."""
    pred = parallel_safe_when("method", "GET")
    assert pred(args) is False


def test_plan_segments():
    """New interface: safe auto-approved runs merge; everything else stands alone."""
    r1, r2, w, r3, cf, r4 = (_c(i) for i in ["r1", "r2", "w", "r3", "cf", "r4"])
    plan = _plan_tool_segments([r1, r2, w, r3, cf, r4],
                               confirm_ids={"cf"}, safe_ids={"r1", "r2", "r3", "r4", "cf"})
    assert [(k, [t.id for t in s]) for k, s in plan] == [
        ("parallel", ["r1", "r2"]), ("parallel", ["w"]), ("parallel", ["r3"]),
        ("confirm", ["cf"]),  # safe but needs confirmation: a barrier, never merged
        ("parallel", ["r4"]),
    ]
    assert _plan_tool_segments([], set(), set()) == []
