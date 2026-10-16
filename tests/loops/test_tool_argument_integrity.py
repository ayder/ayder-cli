"""Truncated or non-object tool arguments never execute (findings F2, F11).

When the model hits its output limit, the streamed JSON arguments are cut
off. ``_repair_truncated_json`` closes the cut string, so a ``file_editor``
write received partial ``content`` and overwrote the file (F2). Valid JSON
that is not an object, such as ``null``, crashed the required-argument check
with ``TypeError`` and left the assistant's tool call without a result (F11).
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from ayder_cli.loops.chat_loop import (
    ChatLoop,
    ChatLoopConfig,
    _check_required_args,
    _parse_tool_arguments,
)
from ayder_cli.providers.base import _FunctionCall, _ToolCall
from ayder_cli.tools.definition import (
    TOOL_DEFINITIONS_BY_NAME,
    ToolDefinition,
    register_dynamic_definition,
)
from ayder_cli.tools.schemas import TOOL_PERMISSIONS

TRUNCATED_WRITE = '{"file_path": "a.py", "operation": "write", "content": "def f():\\n    ret'


class _Registry:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def execute(self, name, arguments):
        self.calls.append((name, dict(arguments)))
        return "ok"

    def get_schemas(self, tags=None):
        return []


class _Callbacks:
    def on_thinking_start(self): ...
    def on_thinking_stop(self): ...
    def on_assistant_content(self, text): ...
    def on_thinking_content(self, text): ...
    def on_token_usage(self, total_tokens): ...
    def on_tool_start(self, call_id, name, arguments): ...
    def on_tool_complete(self, call_id, result): ...
    def on_tools_cleanup(self): ...
    def on_system_message(self, text): ...
    async def request_confirmation(self, name, arguments):
        return SimpleNamespace(action="approve")
    def is_cancelled(self):
        return False


class _Context:
    session_id = None
    run_id = None

    def prepare_messages(self, messages, max_history=0):
        return list(messages)

    def update_from_response(self, usage):
        pass


def _loop(registry):
    return ChatLoop(
        llm=None,
        registry=registry,
        messages=[],
        config=ChatLoopConfig(permissions={"r", "w", "x", "http"}),
        callbacks=_Callbacks(),
        context_manager=_Context(),
    )


def _call(name, arguments, call_id="c1"):
    return _ToolCall(id=call_id, type="function",
                     function=_FunctionCall(name=name, arguments=arguments))


def _run(loop, *calls):
    asyncio.run(loop._execute_tool_calls(list(calls)))
    return {m["tool_call_id"]: m["content"] for m in loop.messages if m["role"] == "tool"}


@pytest.fixture
def dynamic_tool():
    """Register a temporary tool with a chosen permission; always cleaned up."""
    added: list[str] = []

    def make(name, permission):
        td = ToolDefinition(
            name=name, description="test tool",
            func_ref="tests.loops.test_tool_argument_integrity:_unused",
            parameters={"type": "object",
                        "properties": {"text": {"type": "string"}},
                        "required": []},
            permission=permission,
        )
        register_dynamic_definition(td)
        TOOL_PERMISSIONS[name] = permission
        added.append(name)
        return name

    yield make
    for name in added:
        TOOL_DEFINITIONS_BY_NAME.pop(name, None)
        TOOL_PERMISSIONS.pop(name, None)


def _unused(**kwargs):  # pragma: no cover - func_ref target, never imported
    return "unused"


# --- F2: truncated arguments ----------------------------------------------------


def test_truncated_write_is_refused_and_not_executed():
    """Baseline regression: the repaired partial content is written today."""
    registry = _Registry()
    results = _run(_loop(registry), _call("file_editor", TRUNCATED_WRITE))
    assert registry.calls == []
    assert "cut off" in results["c1"] and "nothing was executed" in results["c1"]


def test_truncated_unknown_tool_is_refused():
    """Baseline regression: the result names validation, not truncation, today."""
    registry = _Registry()
    results = _run(_loop(registry), _call("no_such_tool_xyz", '{"text": "abc'))
    assert registry.calls == []
    assert "cut off" in results["c1"]


def test_truncated_dynamic_tool_needs_explicit_r(dynamic_tool):
    """Baseline regression for the 'x' tool (it runs on repaired args today);
    the 'r' tool's recovery is preservation."""
    x_tool = dynamic_tool("t_dyn_exec", "x")
    r_tool = dynamic_tool("t_dyn_read", "r")
    registry = _Registry()
    results = _run(
        _loop(registry),
        _call(x_tool, '{"text": "abc', "cx"),
        _call(r_tool, '{"text": "abc', "cr"),
    )
    assert "cut off" in results["cx"]
    assert registry.calls == [(r_tool, {"text": "abc"})]


def test_truncated_read_only_call_still_recovers(tmp_path):
    """Preservation: a cut-off read_file call is recovered and run."""
    registry = _Registry()
    _run(_loop(registry), _call("read_file", '{"file_path": "a.py", "start_line": 1'))
    assert registry.calls == [("read_file", {"file_path": "a.py", "start_line": 1})]


def test_complete_concatenated_object_is_not_flagged():
    """Preservation: a complete leading object (raw_decode) is not 'repaired'."""
    raw = '{"file_path": "a.py", "operation": "write", "content": "x"} trailing'
    assert _parse_tool_arguments(raw) == (
        {"file_path": "a.py", "operation": "write", "content": "x"}, "ok")
    registry = _Registry()
    _run(_loop(registry), _call("file_editor", raw))
    assert [c[0] for c in registry.calls] == ["file_editor"]


# --- F11: non-object arguments ----------------------------------------------------


@pytest.mark.parametrize(
    "raw", [None, [], 1, True, "null", "[]", "1", '"s"', '[{"file_path": "a"}]']
)
def test_parse_tool_arguments_marks_every_non_dict_invalid(raw):
    """New interface: every non-dict value, raw or JSON-decoded, is invalid."""
    assert _parse_tool_arguments(raw) == ({}, "invalid")


def test_parse_tool_arguments_ok_and_repaired_statuses():
    """New interface: dict, empty and JSON-object input are ok; repair is flagged."""
    assert _parse_tool_arguments({"a": 1}) == ({"a": 1}, "ok")
    assert _parse_tool_arguments("") == ({}, "ok")
    assert _parse_tool_arguments("   ") == ({}, "ok")
    assert _parse_tool_arguments('{"a": 1}') == ({"a": 1}, "ok")
    assert _parse_tool_arguments('{"a": "b') == ({"a": "b"}, "repaired")


def test_null_arguments_return_object_error_without_crash():
    """Baseline regression: TypeError today, and the call gets no tool result."""
    loop = _loop(_Registry())
    loop.messages.append({"role": "assistant", "content": "",
                          "tool_calls": [{"id": "c1", "type": "function",
                                          "function": {"name": "read_file",
                                                       "arguments": "null"}}]})
    results = _run(loop, _call("read_file", "null"))
    assert "must be a JSON object" in results["c1"]


def test_empty_arguments_still_run_no_arg_tool():
    """Preservation: providers send "" for a call with no arguments."""
    registry = _Registry()
    _run(_loop(registry), _call("file_explorer", ""))
    assert registry.calls == [("file_explorer", {})]


def test_loop_gate_matches_policy_for_alias():
    """Preservation: the alias passes the loop gate and reaches the tool canonical."""
    assert _check_required_args("read_file", {"path": "a.py"}) == []
    registry = _Registry()
    _run(_loop(registry), _call("read_file", '{"path": "a.py"}'))
    assert registry.calls == [("read_file", {"file_path": "a.py"})]


class _ScriptedLLM:
    """Streams one scripted response per call (no network)."""

    def __init__(self, *responses):
        self._responses = list(responses)

    async def stream_with_tools(self, messages, model, tools=None, options=None,
                                verbose=False):
        content, tool_calls = self._responses.pop(0)
        yield SimpleNamespace(content=content, reasoning="", tool_calls=tool_calls,
                              usage=None)


def test_history_stores_object_for_non_object_arguments():
    """Baseline regression: history keeps "null" arguments today, which the
    next provider request carries back."""
    tc = SimpleNamespace(id="c1", name="read_file", arguments="null", _stream_index=0)
    llm = _ScriptedLLM(("", [tc]), ("done", []))
    loop = ChatLoop(
        llm=llm, registry=_Registry(), messages=[{"role": "user", "content": "go"}],
        config=ChatLoopConfig(permissions={"r"}), callbacks=_Callbacks(),
        context_manager=_Context(),
    )
    asyncio.run(loop.run())
    assistant = next(m for m in loop.messages if m.get("tool_calls"))
    assert assistant["tool_calls"][0]["function"]["arguments"] == "{}"
    tool = next(m for m in loop.messages if m["role"] == "tool")
    assert "must be a JSON object" in tool["content"]
