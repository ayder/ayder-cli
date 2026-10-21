"""Tool calls in one turn take effect in emission order (audit P0-2).

Before this fix every auto-approved call started at once and confirmation
calls ran after all of them, so a read sent after a write could see the old
file, run before the write was even confirmed, or run after the user had
redirected the turn. Consecutive parallel-safe, auto-approved calls still run
concurrently.

The fake registry logs start/end events per call. Concurrency is proven with
``threading.Barrier`` rendezvous (serial execution breaks the barrier), and
order with log positions, not wall-clock comparisons. No network
(environment: local-faked).
"""

from __future__ import annotations

import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from ayder_cli.loops.chat_loop import ChatLoop, ChatLoopConfig
from ayder_cli.providers.base import _FunctionCall, _ToolCall
from ayder_cli.tools import definition, schemas
from ayder_cli.tools.definition import ToolDefinition

WAIT = 5.0


class _Registry:
    """Logs ``start:``/``end:`` per call; behaviours are keyed by ``name:key``."""

    def __init__(self):
        self.log: list[str] = []
        self.sleep: dict[str, float] = {}
        self.rendezvous: dict[str, threading.Barrier] = {}
        self.release: dict[str, threading.Event] = {}
        self.entered: dict[str, threading.Event] = {}
        self._lock = threading.Lock()

    def _record(self, event):
        with self._lock:
            self.log.append(event)

    def hold(self, slot):
        self.release[slot] = threading.Event()
        self.entered[slot] = threading.Event()

    def execute(self, name, arguments):
        key = arguments["file_path"]
        slot = f"{name}:{key}"
        self._record(f"start:{slot}")
        if slot in self.entered:
            self.entered[slot].set()
            self.release[slot].wait(WAIT)
        if slot in self.sleep:
            time.sleep(self.sleep[slot])
        if slot in self.rendezvous:
            self.rendezvous[slot].wait(timeout=WAIT)
        self._record(f"end:{slot}")
        return f"result:{key}"

    def get_schemas(self, tags=None):
        return []


class _Callbacks:
    def __init__(self, log: list[str]):
        self.log = log
        self.answer = "approve"
        self.cancel_event = threading.Event()

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
        self.log.append(f"confirm:{name}")
        return SimpleNamespace(action=self.answer, instructions="do X instead")

    def is_cancelled(self):
        return self.cancel_event.is_set()


class _Context:
    session_id = None
    run_id = None

    def prepare_messages(self, messages, max_history=0):
        return list(messages)

    def update_from_response(self, usage):
        pass


def _call(key, call_id=None, name="read_file"):
    args = '{"file_path": "%s"}' % key
    if name == "file_editor":
        args = '{"file_path": "%s", "operation": "write", "content": "x"}' % key
    return _ToolCall(id=call_id or f"id_{key}", type="function",
                     function=_FunctionCall(name=name, arguments=args))


def _setup(permissions):
    registry = _Registry()
    cb = _Callbacks(registry.log)
    chat = ChatLoop(
        llm=None, registry=registry, messages=[],
        config=ChatLoopConfig(permissions=set(permissions)),
        callbacks=cb, context_manager=_Context(),
    )
    return registry, cb, chat


def _run(chat, calls):
    async def main():
        asyncio.get_running_loop().set_default_executor(ThreadPoolExecutor(max_workers=8))
        await chat._execute_tool_calls(calls)

    asyncio.run(main())


def _results(chat):
    return {m["tool_call_id"]: m["content"] for m in chat.messages if m["role"] == "tool"}


def _before(log, a, b):
    assert a in log and b in log, log
    assert log.index(a) < log.index(b), log


def _register(monkeypatch, name, permission, **flags):
    td = ToolDefinition(
        name=name, description="x", permission=permission,
        parameters={"type": "object", "properties": {"file_path": {"type": "string"}},
                    "required": ["file_path"]},
        **flags,
    )
    monkeypatch.setitem(definition.TOOL_DEFINITIONS_BY_NAME, name, td)
    monkeypatch.setitem(schemas.TOOL_PERMISSIONS, name, permission)


def test_read_after_auto_write_sees_the_write():
    """Baseline regression D1: the read starts while the write is still running."""
    registry, _cb, chat = _setup({"r", "w"})
    registry.sleep["file_editor:p"] = 0.2
    _run(chat, [_call("p", "id_w", name="file_editor"), _call("p", "id_r")])
    _before(registry.log, "end:file_editor:p", "start:read_file:p")


def test_confirmed_write_is_asked_before_later_read_runs():
    """Baseline regression D2: the read runs before the confirmation dialog opens."""
    registry, _cb, chat = _setup({"r"})
    _run(chat, [_call("p", "id_w", name="file_editor"), _call("p", "id_r")])
    assert registry.log == ["confirm:file_editor", "start:file_editor:p", "end:file_editor:p",
                            "start:read_file:p", "end:read_file:p"]


def test_instruct_skips_later_calls_without_running_them():
    """Baseline regression D3: the later read has already run when the user redirects."""
    registry, cb, chat = _setup({"r"})
    cb.answer = "instruct"
    _run(chat, [_call("p", "id_w", name="file_editor"), _call("q")])
    assert not any(e.startswith("start:") for e in registry.log)
    assert _results(chat) == {"id_w": "Tool call skipped by user instruction.",
                              "id_q": "Tool call skipped."}
    assert chat.messages[-1] == {"role": "user", "content": "do X instead"}


def test_segments_overlap_inside_and_serialize_across():
    """Baseline regression: the write overlaps the reads around it."""
    registry, _cb, chat = _setup({"r", "w"})
    first, second = threading.Barrier(2), threading.Barrier(2)
    registry.rendezvous.update({"read_file:a": first, "read_file:b": first,
                                "read_file:c": second, "read_file:d": second})
    _run(chat, [_call("a"), _call("b"), _call("w", name="file_editor"), _call("c"), _call("d")])
    results = _results(chat)
    assert [results[f"id_{k}"] for k in "abcd"] == ["result:a", "result:b", "result:c", "result:d"]
    _before(registry.log, "end:read_file:a", "start:file_editor:w")
    _before(registry.log, "end:read_file:b", "start:file_editor:w")
    _before(registry.log, "end:file_editor:w", "start:read_file:c")
    _before(registry.log, "end:file_editor:w", "start:read_file:d")


def test_unclassified_dynamic_tool_is_a_barrier(monkeypatch):
    """Baseline regression: a plugin definition that never set parallel_safe."""
    _register(monkeypatch, "plugin_x", "r")
    registry, _cb, chat = _setup({"r"})
    registry.sleep["plugin_x:a"] = 0.2
    _run(chat, [_call("a", name="plugin_x"), _call("b", name="plugin_x")])
    _before(registry.log, "end:plugin_x:a", "start:plugin_x:b")


def test_cancel_in_first_segment_never_runs_later_segment():
    """Baseline regression: the write runs alongside the held read."""
    registry, cb, chat = _setup({"r", "w"})
    registry.hold("read_file:a")

    async def main():
        asyncio.get_running_loop().set_default_executor(ThreadPoolExecutor(max_workers=8))
        task = asyncio.create_task(
            chat._execute_tool_calls([_call("a"), _call("w", name="file_editor")]))
        deadline = time.monotonic() + WAIT
        while not registry.entered["read_file:a"].is_set():
            assert time.monotonic() < deadline, "read never started"
            await asyncio.sleep(0.005)
        await asyncio.sleep(0.1)  # a concurrent write would start now
        cb.cancel_event.set()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        registry.release["read_file:a"].set()
        await asyncio.sleep(0.3)

    asyncio.run(main())
    assert "start:file_editor:w" not in registry.log
    assert "cancelled before it ran" in _results(chat)["id_w"]


def test_mcp_fan_out_runs_concurrently(monkeypatch):
    """Preservation: MCP calls fan out concurrently and must keep doing so."""
    _register(monkeypatch, "mcp_search", "http", parallel_safe=True)
    registry, _cb, chat = _setup({"r", "http"})
    meet = threading.Barrier(3)
    registry.rendezvous.update({f"mcp_search:{k}": meet for k in "abc"})
    _run(chat, [_call(k, name="mcp_search") for k in "abc"])
    assert _results(chat) == {"id_a": "result:a", "id_b": "result:b", "id_c": "result:c"}


def test_consecutive_reads_still_run_concurrently():
    """Preservation: three reads rendezvous; serial execution would break the barrier."""
    registry, _cb, chat = _setup({"r"})
    meet = threading.Barrier(3)
    registry.rendezvous.update({f"read_file:{k}": meet for k in "abc"})
    _run(chat, [_call(k) for k in "abc"])
    assert _results(chat) == {"id_a": "result:a", "id_b": "result:b", "id_c": "result:c"}


def test_mixed_batch_history_in_emission_order():
    """Preservation: tool messages are appended in emission order."""
    registry, _cb, chat = _setup({"r", "w"})
    registry.sleep["read_file:a"] = 0.2
    _run(chat, [_call("a"), _call("b"), _call("w", name="file_editor"), _call("c")])
    assert [m["tool_call_id"] for m in chat.messages if m["role"] == "tool"] == \
        ["id_a", "id_b", "id_w", "id_c"]
