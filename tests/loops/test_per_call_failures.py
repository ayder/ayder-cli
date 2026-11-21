"""A failure inside one tool call becomes that call's result (plan step 2, R6).

Before this step a policy, a registry or a callback that raised while a
confirmed call ran escaped ``run()``; a ``parallel_safe`` predicate that raised
did the same; and a parallel call's failure reached history as the raw
exception text, unbounded, while the batch's own record held the bounded text.
Now each failure is the call's result, bounded once, and the batch goes on.
A real task cancellation still propagates.

Kind: baseline regression unless a docstring says preservation. Environment:
local-faked (no network; the provider, callbacks and registry are the fakes in
``turn_fakes``). Layer: unit.

Every red case is driven by real inputs: a registry that raises (tool, plugin
and middleware code do), an ``is_cancelled`` callback that raises, a tool whose
definition carries a raising ``parallel_safe`` predicate, and
``_exec_tool_async`` called directly (it is called, not changed).
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any, Callable

import pytest

from ayder_cli.loops.chat_loop import ChatLoop, _ToolBatch, _truncate_for_tool
from ayder_cli.providers.base import _FunctionCall, _ToolCall
from ayder_cli.tools.definition import (
    TOOL_DEFINITIONS_BY_NAME,
    ToolDefinition,
    register_dynamic_definition,
)
from ayder_cli.tools.schemas import TOOL_PERMISSIONS
from tests.loops.turn_fakes import (
    RecordingCallbacks,
    RecordingRegistry,
    ScriptedProvider,
    chunk,
    delta,
    make_loop,
    run_turn,
    tool_messages,
)

WAIT = 5.0
_READ = '{"file_path": "a.py"}'
_WRITE = '{"file_path": "a.py", "operation": "write", "content": "x"}'
_GUARD_WARNING = "raised; continuing without it"
_CANCEL_TEXT = "Error: Tool execution cancelled"


def _escape(fn: Callable[..., Any], *args: Any) -> BaseException | None:
    """What leaves ``fn(*args)``, or None. Lets a test assert that nothing escaped."""
    try:
        fn(*args)
    except BaseException as exc:  # noqa: BLE001 - the test wants whatever escaped
        return exc
    return None


def _call(call_id: str, name: str, arguments: str) -> _ToolCall:
    return _ToolCall(
        id=call_id, type="function", function=_FunctionCall(name=name, arguments=arguments)
    )


def _results(loop: ChatLoop) -> dict[str, str]:
    return {m["tool_call_id"]: m["content"] for m in tool_messages(loop)}


def _confirmed_write_loop(registry, callbacks=None, extra_calls=()):
    """A loop whose first reply asks for a confirmed write, then more calls."""
    calls = [delta("c1", "file_editor", _WRITE), *extra_calls]
    provider = ScriptedProvider([chunk(calls=calls)], [chunk(content="done")])
    return make_loop(
        provider, registry=registry, callbacks=callbacks or RecordingCallbacks(), permissions={"r"}
    )


class _OverlapRegistry(RecordingRegistry):
    """Says whether a call started while its neighbour was still running.

    Each call sets its own "started" event, then waits briefly for the event of
    the call listed for it in ``waits``. Calls in one parallel segment run in
    parallel, so the awaited event arrives. A barrier call cannot start until
    the call before it has finished, so the wait always times out and
    ``overlapped`` stays False, whatever the machine's speed.
    """

    PATIENCE = 0.3

    def __init__(self, keys: Callable[[str, dict], str], waits: dict[str, str]) -> None:
        super().__init__()
        self._keys = keys
        self._waits = waits
        self.started = {key: threading.Event() for key in (*waits, *waits.values())}
        self.overlapped: dict[str, bool] = {}

    def execute(self, name: str, arguments: dict) -> Any:
        key = self._keys(name, arguments)
        self.started[key].set()
        awaited = self._waits.get(key)
        if awaited is not None:
            self.overlapped[key] = self.started[awaited].wait(self.PATIENCE)
        return super().execute(name, arguments)


@pytest.fixture
def probe_tool():
    """Register temporary tools through the table ``is_parallel_safe`` reads."""
    added: list[str] = []

    def make(name, *, parallel_safe=True, max_result_chars=None):
        definition = ToolDefinition(
            name=name,
            description="test tool",
            func_ref="tests.loops.test_per_call_failures:_unused",
            parameters={"type": "object", "properties": {}, "required": []},
            permission="r",
            parallel_safe=parallel_safe,
            max_result_chars=max_result_chars,
        )
        register_dynamic_definition(definition)
        TOOL_PERMISSIONS[name] = "r"
        added.append(name)
        return name

    yield make
    for name in added:
        TOOL_DEFINITIONS_BY_NAME.pop(name, None)
        TOOL_PERMISSIONS.pop(name, None)


def _unused(**kwargs):  # pragma: no cover - func_ref target, never imported
    return "unused"


# -- A confirmed call that fails ---------------------------------------------


def test_a_confirmed_call_that_raises_becomes_its_result_and_the_batch_goes_on():
    """Baseline regression: a middleware's ``PermissionError`` escapes ``run()`` today (B4).

    Driven by a registry that raises. After: the result is ``Error: <exception>``,
    the next call runs and the turn completes.
    """
    registry = RecordingRegistry(raises={"file_editor": PermissionError("blocked by middleware")})
    loop = _confirmed_write_loop(registry, extra_calls=[delta("c2", "read_file", _READ)])

    escaped = _escape(run_turn, loop)

    assert escaped is None
    assert _results(loop) == {"c1": "Error: blocked by middleware", "c2": "ok"}
    assert loop.cb.completes_by_key()["c1"] == ["Error: blocked by middleware"]
    assert [name for name, _ in registry.calls] == ["file_editor", "read_file"]
    assert loop.outcome is not None and loop.outcome.status == "completed"


def test_a_stray_cancellation_in_a_confirmed_call_becomes_its_result():
    """Baseline regression: a bare ``CancelledError`` from a confirmed call escapes ``run()`` today.

    Driven by a registry that raises ``asyncio.CancelledError()`` with no argument, as tool
    code does when a library cancels a future it awaits. After: the result is
    ``Error: Tool execution cancelled`` and the turn completes.
    """
    registry = RecordingRegistry(raises={"file_editor": asyncio.CancelledError()})
    loop = _confirmed_write_loop(registry)

    escaped = _escape(run_turn, loop)

    assert escaped is None
    assert _results(loop) == {"c1": _CANCEL_TEXT}
    assert loop.outcome is not None and loop.outcome.status == "completed"


def test_a_cancel_poll_that_raises_in_a_confirmed_worker_becomes_its_result():
    """Baseline regression: ``is_cancelled`` raising in the worker's start check escapes today.

    Driven by an ``is_cancelled`` callback that raises when a worker thread asks, as the spec's
    "callbacks that raise" allows. After: it is that call's result and the tool never starts.
    """
    test_thread = threading.get_ident()

    def poll_fails_in_a_worker():
        if threading.get_ident() != test_thread:
            raise RuntimeError("cancel poll exploded")

    callbacks = RecordingCallbacks(raises={"is_cancelled": poll_fails_in_a_worker})
    registry = RecordingRegistry()
    loop = _confirmed_write_loop(registry, callbacks)

    escaped = _escape(run_turn, loop)

    assert escaped is None
    assert _results(loop) == {"c1": "Error: cancel poll exploded"}
    assert registry.calls == []
    assert loop.outcome is not None and loop.outcome.status == "completed"


# -- A predicate that raises --------------------------------------------------


def test_a_parallel_safe_predicate_that_raises_runs_its_call_alone_with_one_warning(
    probe_tool, loguru_caplog
):
    """Baseline regression: a raising ``parallel_safe`` predicate escapes ``run()`` today (E13).

    Driven by a tool whose registered definition carries the raising predicate. After: the call
    still runs, in emission order between its neighbours, and the guard logs one warning. It is
    a barrier: it starts only after the call before it has finished, and the call after it
    starts only after it has finished.
    """

    def predicate(args):
        raise ValueError("predicate exploded")

    name = probe_tool("probe_tool", parallel_safe=predicate)
    provider = ScriptedProvider(
        [
            chunk(
                calls=[
                    delta("c1", "read_file", _READ),
                    delta("c2", name, "{}"),
                    delta("c3", "read_file", '{"file_path": "b.py"}'),
                ]
            )
        ],
        [chunk(content="done")],
    )
    registry = _OverlapRegistry(
        keys=lambda tool, args: "probe" if tool == name else args["file_path"],
        # a.py waits for the probe to start; the probe waits for b.py to start
        waits={"a.py": "probe", "probe": "b.py"},
    )
    loop = make_loop(provider, registry=registry)

    escaped = _escape(run_turn, loop)

    assert escaped is None
    assert registry.overlapped == {"a.py": False, "probe": False}
    assert [call[0] for call in registry.calls] == ["read_file", name, "read_file"]
    assert _results(loop) == {"c1": "ok", "c2": "ok", "c3": "ok"}
    warnings = [m for m in loguru_caplog.only("warning").messages if _GUARD_WARNING in m]
    assert warnings == ["parallel_safe predicate raised; continuing without it"]


# -- What the worker records and what history holds --------------------------


def test_a_raised_cancellation_is_recorded_with_the_text_settlement_writes():
    """Baseline regression: ``_exec_tool_async`` records ``Error: `` for a bare ``CancelledError``.

    Called directly, with a registry that raises ``asyncio.CancelledError()``. The exception
    still reaches the waiter; the record now reads ``Error: Tool execution cancelled``.
    """
    registry = RecordingRegistry(raises={"read_file": asyncio.CancelledError()})
    loop = make_loop(ScriptedProvider([chunk()]), registry=registry)
    batch = _ToolBatch()
    call = _call("c1", "read_file", _READ)

    async def go() -> str:
        try:
            await loop._exec_tool_async(call, batch)
        except asyncio.CancelledError:
            return "raised"
        return "returned"

    assert asyncio.run(go()) == "raised"
    assert batch.results["c1"]["result"] == _CANCEL_TEXT


def test_a_cancel_poll_that_raises_before_the_start_is_recorded():
    """Baseline regression: a raise in the worker's start check leaves no record today.

    Called directly, with an ``is_cancelled`` callback that raises. The exception still reaches
    the waiter; the bounded ``Error: ...`` dict is recorded first, so a settlement that runs
    before collection has the call's real result instead of the cancel text.
    """
    callbacks = RecordingCallbacks(raises={"is_cancelled": RuntimeError("cancel poll exploded")})
    registry = RecordingRegistry()
    loop = make_loop(ScriptedProvider([chunk()]), registry=registry, callbacks=callbacks)
    batch = _ToolBatch()
    call = _call("c1", "read_file", _READ)

    async def go() -> BaseException | None:
        try:
            await loop._exec_tool_async(call, batch)
        except Exception as exc:  # noqa: BLE001 - the test reads what the waiter gets
            return exc
        return None

    raised = asyncio.run(go())

    assert isinstance(raised, RuntimeError)
    assert "c1" in batch.results
    assert batch.results["c1"]["result"] == "Error: cancel poll exploded"
    assert registry.calls == []


def test_a_parallel_cancellation_reaches_history_as_the_same_text():
    """Preservation: the collector turns a stray cancellation into ``Error: Tool execution cancelled``.

    The same registry as the confirmed case, on the parallel path the collector reads. Passes
    before and after.
    """
    registry = RecordingRegistry(raises={"read_file": asyncio.CancelledError()})
    provider = ScriptedProvider([chunk(calls=[delta("c1", "read_file", _READ)])], [chunk(content="ok")])
    loop = make_loop(provider, registry=registry)

    run_turn(loop)

    assert _results(loop) == {"c1": _CANCEL_TEXT}
    assert loop.cb.completes_by_key() == {"c1": [_CANCEL_TEXT]}
    assert loop.outcome is not None and loop.outcome.status == "completed"


def test_a_parallel_failure_is_bounded_in_history_the_ui_and_the_record(probe_tool):
    """Baseline regression: history holds the unbounded ``Error: ...`` text; the record is bounded.

    A parallel call whose registry raises a message far longer than the tool's bound. After:
    history, ``on_tool_complete`` and the worker's own record carry the same bounded text.
    """
    name = probe_tool("probe_tool")
    message = "x" * 120_000
    registry = RecordingRegistry(raises={name: RuntimeError(message)})
    provider = ScriptedProvider([chunk(calls=[delta("c1", name, "{}")])], [chunk(content="done")])
    loop = make_loop(provider, registry=registry)
    batch = _ToolBatch()

    async def record() -> None:
        try:
            await loop._exec_tool_async(_call("c1", name, "{}"), batch)
        except RuntimeError:
            pass

    asyncio.run(record())
    bounded = batch.results["c1"]["result"]
    run_turn(loop)

    assert bounded == _truncate_for_tool(name, f"Error: {message}")
    assert len(bounded) < 40_000
    assert _results(loop) == {"c1": bounded}
    assert loop.cb.completes_by_key() == {"c1": [bounded]}


# -- A real cancellation still propagates ------------------------------------


def test_a_task_cancelled_while_a_confirmed_call_runs_still_re_raises_with_history_settled():
    """Preservation: only a stray cancellation becomes a result; a task cancellation propagates.

    Ctrl+X cancels the turn's task while the confirmed call's worker runs. The task ends
    cancelled and the call still has its one tool message. Passes before and after.
    """
    entered, release = threading.Event(), threading.Event()

    class HeldRegistry(RecordingRegistry):
        def execute(self, name: str, arguments: dict) -> Any:
            entered.set()
            release.wait(WAIT)
            return super().execute(name, arguments)

    loop = _confirmed_write_loop(HeldRegistry())

    async def main() -> str:
        task = asyncio.create_task(loop.run())
        await asyncio.wait_for(asyncio.to_thread(entered.wait, WAIT), WAIT)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            assert task.cancelled()
            return "raised"
        finally:
            # Only now may the worker finish: settlement has already run.
            release.set()
        return "returned"

    assert asyncio.run(main()) == "raised"
    (message,) = tool_messages(loop)
    assert message["tool_call_id"] == "c1"
    assert "interrupted while running" in message["content"]
    assert loop.outcome is not None and loop.outcome.status == "cancelled"


# -- The guard ---------------------------------------------------------------


@pytest.mark.parametrize(
    "exc", [RuntimeError("boom"), asyncio.CancelledError()], ids=["exception", "stray-cancellation"]
)
def test_the_guard_returns_its_default_reports_the_failure_and_warns_once(exc, loguru_caplog):
    """New interface: ``_guarded`` turns a raising call into its default.

    Called with a function that raises. It returns ``default``, hands the exception to
    ``on_error`` and logs one warning with the traceback, for an ``Exception`` and for a stray
    ``CancelledError`` alike.
    """
    loop = make_loop(ScriptedProvider([chunk()]))
    seen: list[BaseException] = []
    returned: list[Any] = []

    def boom():
        raise exc

    escaped = _escape(
        lambda: returned.append(
            loop._guarded("probe", boom, default="fallback", on_error=seen.append)
        )
    )

    assert escaped is None
    assert returned == ["fallback"]
    assert seen == [exc]
    (record,) = [r for r in loguru_caplog.records if _GUARD_WARNING in r["message"]]
    assert record["message"] == "probe raised; continuing without it"
    assert record["level"].name == "WARNING"
    assert record["extra"]["channel"] == "llm"
    assert record["exception"] is not None
