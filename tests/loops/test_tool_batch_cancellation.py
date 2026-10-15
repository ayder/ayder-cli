"""A cancelled tool batch settles every call exactly once (finding F3).

Ctrl+C cancels the turn task while ``_execute_tool_calls`` awaits its worker
threads. Before this fix the batch was abandoned: the assistant message with
``tool_calls`` stayed in history without results (so the next request was
malformed), queued workers still started after the cancel, and a confirmed
call's completion event was lost when its waiter was cancelled.

Workers block on ``threading.Event``s in a fake registry. The event loop's
default executor is replaced with a one-thread pool, so a second call stays
queued while the first runs. No network (environment: local-faked).
"""

from __future__ import annotations

import asyncio
import gc
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from ayder_cli.core.result import ToolError
from ayder_cli.loops.chat_loop import ChatLoop, ChatLoopConfig
from ayder_cli.providers.base import _FunctionCall, _ToolCall

WAIT = 5.0


class _Registry:
    """read_file calls keyed by file_path; each can be held and released."""

    def __init__(self, fail: frozenset[str] = frozenset()):
        self.calls: list[str] = []
        self.entered: dict[str, threading.Event] = {}
        self.finished: dict[str, threading.Event] = {}
        self.release: dict[str, threading.Event] = {}
        self._fail = fail
        self._lock = threading.Lock()

    def _ev(self, table, key):
        with self._lock:
            return table.setdefault(key, threading.Event())

    def hold(self, key):
        self._ev(self.release, key)

    def execute(self, name, arguments):
        key = arguments["file_path"].rsplit("/", 1)[-1]
        self.calls.append(key)
        self._ev(self.entered, key).set()
        gate = self.release.get(key)
        if gate is not None:
            gate.wait(WAIT)
        self._ev(self.finished, key).set()
        if key in self._fail:
            return ToolError(f"boom:{key}", "execution")
        return f"result:{key}"

    def get_schemas(self, tags=None):
        return []


class _Callbacks:
    def __init__(self):
        self.cancel_event = threading.Event()
        self.completed: list[tuple[str, str]] = []
        self.confirm_gate: asyncio.Event | None = None
        self.raise_on_tool_start = False
        self.raise_on_cleanup = False

    def on_thinking_start(self): ...
    def on_thinking_stop(self): ...
    def on_assistant_content(self, text): ...
    def on_thinking_content(self, text): ...
    def on_token_usage(self, total_tokens): ...
    def on_tool_start(self, call_id, name, arguments):
        if self.raise_on_tool_start:
            raise RuntimeError("ui exploded")
    def on_tool_complete(self, call_id, result):
        self.completed.append((call_id, result))
    def on_tools_cleanup(self):
        if self.raise_on_cleanup:
            raise RuntimeError("cleanup exploded")
    def on_system_message(self, text): ...
    async def request_confirmation(self, name, arguments):
        if self.confirm_gate is not None:
            await self.confirm_gate.wait()
        return SimpleNamespace(action="approve")
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


def _chat(registry, callbacks, permissions=frozenset({"r"})):
    return ChatLoop(
        llm=None, registry=registry, messages=[],
        config=ChatLoopConfig(permissions=set(permissions)),
        callbacks=callbacks, context_manager=_Context(),
    )


def _tool_messages(chat):
    return [m for m in chat.messages if m["role"] == "tool"]


def _by_id(chat):
    msgs = _tool_messages(chat)
    ids = [m["tool_call_id"] for m in msgs]
    assert len(ids) == len(set(ids)), f"duplicate tool results: {ids}"
    return {m["tool_call_id"]: m["content"] for m in msgs}


async def _until(event: threading.Event):
    deadline = time.monotonic() + WAIT
    while not event.is_set():
        assert time.monotonic() < deadline, "timed out waiting for a worker"
        await asyncio.sleep(0.005)


async def _cancel(chat, callbacks, task):
    callbacks.cancel_event.set()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


def _scenario(body):
    async def main():
        asyncio.get_running_loop().set_default_executor(ThreadPoolExecutor(max_workers=1))
        await body()

    asyncio.run(main())


# --- parallel batch ---------------------------------------------------------------


def test_cancel_during_parallel_batch_appends_result_for_every_call():
    """Baseline regression: no tool messages are appended today."""
    registry, cb = _Registry(), _Callbacks()
    registry.hold("a")
    chat = _chat(registry, cb)
    calls = [_call("a"), _call("b"), _call("c")]

    async def body():
        task = asyncio.create_task(chat._execute_tool_calls(calls))
        await _until(registry._ev(registry.entered, "a"))
        await _cancel(chat, cb, task)
        assert [m["tool_call_id"] for m in _tool_messages(chat)] == [c.id for c in calls]
        registry.release["a"].set()

    _scenario(body)


def test_in_flight_call_is_reported_as_interrupted():
    """Baseline regression."""
    registry, cb = _Registry(), _Callbacks()
    registry.hold("a")
    chat = _chat(registry, cb)

    async def body():
        task = asyncio.create_task(chat._execute_tool_calls([_call("a"), _call("b")]))
        await _until(registry._ev(registry.entered, "a"))
        await _cancel(chat, cb, task)
        results = _by_id(chat)
        assert "interrupted" in results["id_a"] and "partially applied" in results["id_a"]
        assert "cancelled before it ran" in results["id_b"]
        registry.release["a"].set()

    _scenario(body)


@pytest.mark.parametrize("fails", [False, True])
def test_completed_but_uncollected_result_is_used(fails):
    """Baseline regression: a worker finished before the cancel, but the batch
    had not collected it yet. History must carry its real result (or its real
    failure), not an 'interrupted' placeholder."""
    registry = _Registry(fail=frozenset({"a"}) if fails else frozenset())
    cb = _Callbacks()
    registry.hold("a")
    chat = _chat(registry, cb)

    async def body():
        task = asyncio.create_task(chat._execute_tool_calls([_call("a")]))
        await _until(registry._ev(registry.entered, "a"))
        registry.release["a"].set()
        # Block the event loop so the finished result cannot be collected.
        assert registry._ev(registry.finished, "a").wait(WAIT)
        time.sleep(0.2)  # let the worker thread record its result
        await _cancel(chat, cb, task)
        result = _by_id(chat)["id_a"]
        assert ("boom:a" if fails else "result:a") in result
        assert "interrupted" not in result

    _scenario(body)


def test_queued_worker_never_runs_after_cancel():
    """Baseline regression: the queued call still executes today."""
    registry, cb = _Registry(), _Callbacks()
    registry.hold("a")
    chat = _chat(registry, cb)

    async def body():
        task = asyncio.create_task(chat._execute_tool_calls([_call("a"), _call("b")]))
        await _until(registry._ev(registry.entered, "a"))
        await _cancel(chat, cb, task)
        registry.release["a"].set()
        await asyncio.sleep(0.3)  # the queued worker gets the thread now
        assert registry.calls == ["a"]

    _scenario(body)


def test_cancelled_batch_worker_stays_cancelled_after_callback_rebinding():
    """Baseline regression: the TUI gives each turn a fresh cancel event. A
    queued worker of cancelled batch A must not run when it finally starts
    during turn B, whose event is unset."""
    registry, cb = _Registry(), _Callbacks()
    registry.hold("a")
    chat = _chat(registry, cb)

    async def body():
        task = asyncio.create_task(chat._execute_tool_calls([_call("a"), _call("b")]))
        await _until(registry._ev(registry.entered, "a"))
        await _cancel(chat, cb, task)
        cb.cancel_event = threading.Event()  # turn B: fresh, unset
        registry.release["a"].set()
        await asyncio.sleep(0.3)
        assert registry.calls == ["a"]

    _scenario(body)


# --- confirmation path ----------------------------------------------------------


def test_cancel_during_confirmation_settles_history():
    """Baseline regression: the call awaiting confirmation gets no result today."""
    registry, cb = _Registry(), _Callbacks()
    cb.confirm_gate = asyncio.Event()  # never set: the dialog stays open
    chat = _chat(registry, cb)

    async def body():
        cb.confirm_gate = asyncio.Event()
        task = asyncio.create_task(
            chat._execute_tool_calls([_call("w", name="file_editor")]))
        await asyncio.sleep(0.05)
        await _cancel(chat, cb, task)
        assert "cancelled before it ran" in _by_id(chat)["id_w"]
        assert registry.calls == []

    _scenario(body)


def test_cancel_during_confirmed_running_call_reports_interrupted_and_emits_completion():
    """Baseline regression: history has no result and the tool_call event is
    lost when the confirmed call's waiter is cancelled. The late completion
    must not reach history or the UI."""
    registry, cb = _Registry(), _Callbacks()
    registry.hold("w")
    chat = _chat(registry, cb)
    emitted: list[str] = []
    chat._emit_tool_call = lambda name, args, started, exec_result: emitted.append(name)

    async def body():
        task = asyncio.create_task(
            chat._execute_tool_calls([_call("w", name="file_editor")]))
        await _until(registry._ev(registry.entered, "w"))
        await _cancel(chat, cb, task)
        assert "interrupted" in _by_id(chat)["id_w"]
        history_len, ui_len = len(chat.messages), len(cb.completed)
        registry.release["w"].set()
        await asyncio.sleep(0.3)
        assert emitted == ["file_editor"]
        assert len(chat.messages) == history_len
        assert len(cb.completed) == ui_len

    _scenario(body)


# --- other exceptions -------------------------------------------------------------


def test_exception_in_callback_settles_history_once():
    """Baseline regression: a raising UI callback leaves no tool results today."""
    registry, cb = _Registry(), _Callbacks()
    cb.raise_on_tool_start = True
    chat = _chat(registry, cb)

    async def body():
        with pytest.raises(RuntimeError, match="ui exploded"):
            await chat._execute_tool_calls([_call("a"), _call("b")])
        assert set(_by_id(chat)) == {"id_a", "id_b"}

    _scenario(body)


def test_exception_in_preprocessing_settles_history_once(monkeypatch):
    """Baseline regression: a raise while sorting calls leaves earlier refusals
    and later calls without results today."""
    registry, cb = _Registry(), _Callbacks()
    chat = _chat(registry, cb)
    refused = _ToolCall(id="id_null", type="function",
                        function=_FunctionCall(name="read_file", arguments="null"))

    def boom(name):
        raise RuntimeError("policy exploded")

    monkeypatch.setattr(chat, "_tool_needs_confirmation", boom)

    async def body():
        with pytest.raises(RuntimeError, match="policy exploded"):
            await chat._execute_tool_calls([refused, _call("b")])
        results = _by_id(chat)
        assert "must be a JSON object" in results["id_null"]
        assert "cancelled before it ran" in results["id_b"]

    _scenario(body)


def test_exception_after_append_does_not_duplicate():
    """Preservation: a raise after the normal append adds no second result."""
    registry, cb = _Registry(), _Callbacks()
    cb.raise_on_cleanup = True
    chat = _chat(registry, cb)

    async def body():
        with pytest.raises(RuntimeError, match="cleanup exploded"):
            await chat._execute_tool_calls([_call("a"), _call("b")])
        assert _by_id(chat) == {"id_a": "result:a", "id_b": "result:b"}

    _scenario(body)


def test_late_task_failure_is_retrieved():
    """New interface: a retained worker task that ends with an exception is
    retrieved by its done-callback, so asyncio reports nothing unretrieved."""
    reported: list[dict] = []

    async def main():
        loop = asyncio.get_running_loop()
        loop.set_exception_handler(lambda _loop, ctx: reported.append(ctx))
        chat = _chat(_Registry(), _Callbacks())

        async def fails():
            raise ValueError("late failure")

        task = asyncio.create_task(fails())
        chat._inflight_tasks.add(task)
        task.add_done_callback(chat._reap_task)
        await asyncio.sleep(0.01)
        assert task not in chat._inflight_tasks
        del task
        gc.collect()
        await asyncio.sleep(0)

    asyncio.run(main())
    assert reported == []


def test_cancelled_error_still_propagates():
    """Preservation: Ctrl+C still ends the batch with CancelledError."""
    registry, cb = _Registry(), _Callbacks()
    registry.hold("a")
    chat = _chat(registry, cb)

    async def body():
        task = asyncio.create_task(chat._execute_tool_calls([_call("a")]))
        await _until(registry._ev(registry.entered, "a"))
        await _cancel(chat, cb, task)  # asserts CancelledError
        registry.release["a"].set()

    _scenario(body)


def test_normal_batch_history_unchanged():
    """Preservation: an uncancelled batch appends the same messages, in order."""
    registry, cb = _Registry(), _Callbacks()
    chat = _chat(registry, cb)

    async def body():
        await chat._execute_tool_calls([_call("a"), _call("b")])

    _scenario(body)
    assert chat.messages == [
        {"role": "tool", "tool_call_id": "id_a", "name": "read_file",
         "content": "result:a"},
        {"role": "tool", "tool_call_id": "id_b", "name": "read_file",
         "content": "result:b"},
    ]
