"""A cancelled turn ends cancelled and propagates (plan step 6, R1, R2).

Before this step a task cancelled while the stream awaited was swallowed by the stream's own
handler, so ``run()`` returned normally: an agent's deadline never fired and a CLI Ctrl+C was not
a ``KeyboardInterrupt``. A stray ``CancelledError`` raised by a provider was taken for a
cancellation, and a ``KeyboardInterrupt`` or a cancellation requested while the turn ended left a
``failed`` outcome published. Now a real task cancellation re-raises with the outcome
``cancelled``, a stray one is an ordinary ``failed`` turn, and a ``BaseException`` that leaves the
turn publishes ``cancelled`` as it propagates.

Kind: baseline regression unless a docstring says preservation. Environment: local-faked (no
network; the provider, callbacks and registry are the fakes in ``turn_fakes``). Layer: unit.

Every case is a real input: ``Task.cancel()`` while the turn is parked, a provider that raises
``CancelledError()`` as an SDK can, a receiver that raises ``KeyboardInterrupt``, cancels its own
task or raises SIGINT, and a hook that recovers a ``TaskGroup`` failure. Where a docstring says
"premise", that assertion already holds on the parent and only sets the scene.
"""

from __future__ import annotations

import asyncio
import signal
from typing import Any

import pytest
from loguru import logger

from ayder_cli.loops.chat_loop import TurnOutcome
from tests.loops.turn_fakes import (
    HeldRegistry,
    RecordingCallbacks,
    ScriptedProvider,
    Stall,
    WaitingConfirmation,
    cancel_parked_turn,
    chunk,
    delta,
    escape,
    make_loop,
    run_turn,
    tool_messages,
)

WAIT = 5.0
_CANCELLED = TurnOutcome("cancelled")
_READ = '{"file_path": "a.py"}'
_WRITE = '{"file_path": "a.py", "operation": "write", "content": "x"}'
_STOP_WARNING = "closing thinking stop raised; continuing without it"
_EVENT_WARNING = "iteration event raised; continuing without it"


def _warnings(caplog, text: str) -> list[str]:
    return [m for m in caplog.only("warning").messages if "raised; continuing without it" in m]


def _stalled_stream_loop(variant: str):
    """A turn parked in the stream; ``variant`` says whether the closing stop will raise."""
    stall = Stall()
    if variant == "plain":
        return make_loop(ScriptedProvider([chunk(content="partial"), stall])), stall
    callbacks = RecordingCallbacks(raises={"on_thinking_stop": RuntimeError("stop exploded")})
    # Reasoning opens a thinking phase that only the closing stop ends.
    provider = ScriptedProvider([chunk(reasoning="thinking"), stall])
    return make_loop(provider, callbacks=callbacks), stall


_STREAM_VARIANTS = pytest.mark.parametrize("variant", ["plain", "closing-stop-raises"])


# -- A task cancelled in the stream (E8) -------------------------------------


@_STREAM_VARIANTS
def test_a_task_cancelled_in_the_stream_re_raises(variant):
    """Baseline regression, E8: the stream swallows the cancellation and ``run()`` returns (B2).

    Driven by ``Task.cancel()`` while the stream awaits. After: ``run()`` re-raises
    ``CancelledError``, even when the closing stop raises while it unwinds.
    """
    loop, stall = _stalled_stream_loop(variant)

    ended, _ = cancel_parked_turn(loop, stall.entered.wait)

    assert ended == "raised"


@_STREAM_VARIANTS
def test_a_task_cancelled_in_the_stream_publishes_only_the_cancelled_state(variant, loguru_caplog):
    """Preservation, E8: whether ``run()`` returns or re-raises, the turn is ``cancelled`` and quiet.

    The outcome has no stage or message and ``reported`` False, ``loop.error`` is None, nothing
    is reported, the task's cancel count is still 1, and a raising closing stop is one guard
    warning. Passes before and after.
    """
    loop, stall = _stalled_stream_loop(variant)

    _, task = cancel_parked_turn(loop, stall.entered.wait)

    assert loop.outcome == _CANCELLED
    assert loop.error is None
    assert loop.cb.system == []
    assert task.cancelling() == 1
    expected = [] if variant == "plain" else [_STOP_WARNING]
    assert _warnings(loguru_caplog, "") == expected


def test_a_cancelled_turn_logs_one_info_record_with_its_stage(loguru_caplog):
    """Baseline regression, E8: today's record says "LLM stream cancelled" with no stage.

    Driven by ``Task.cancel()`` while the stream awaits. After: one info record, "Chat turn
    cancelled (stage=llm)".
    """
    loop, stall = _stalled_stream_loop("plain")

    cancel_parked_turn(loop, stall.entered.wait)

    cancelled = [m for m in loguru_caplog.only("info").messages if "cancelled" in m]
    assert cancelled == ["Chat turn cancelled (stage=llm)"]


# -- A stray CancelledError (E19) ---------------------------------------------


def _stray_cancellation_loop():
    # What a provider SDK can do: raise CancelledError() with no task cancellation behind it.
    return make_loop(ScriptedProvider([chunk(content="partial"), asyncio.CancelledError()]))


def test_a_stray_cancellation_from_the_provider_fails_the_turn_at_the_llm_stage():
    """Baseline regression, E19: the turn returns normally as ``cancelled`` with no error today (X6).

    Driven by a provider that raises ``CancelledError()`` after some content, with nothing having
    cancelled the task (premise: nothing escapes ``run()``). After: ``failed``/``llm``, reported,
    with the class name as the message because the exception has no text.
    """
    loop = _stray_cancellation_loop()

    escaped = escape(run_turn, loop)

    assert escaped is None
    assert loop.outcome == TurnOutcome("failed", "llm", "Error: CancelledError", True)
    assert loop.error == "Error: CancelledError"
    assert loop.cb.system == ["Error: CancelledError"]


def test_a_stray_cancellation_logs_one_error_record_with_a_traceback(loguru_caplog):
    """Baseline regression, E19: no error record is logged today.

    Same input. After: one error record, "Chat turn raised a stray cancellation (stage=llm)",
    with the traceback.
    """
    loop = _stray_cancellation_loop()

    run_turn(loop)

    records = loguru_caplog.only("error").records
    assert [r["message"] for r in records] == ["Chat turn raised a stray cancellation (stage=llm)"]
    assert records[0]["exception"] is not None


# -- A BaseException that leaves the turn ------------------------------------


def _await_run_expecting(loop, exc_type):
    async def go():
        with pytest.raises(exc_type):
            await loop.run()

    asyncio.run(go())


def test_a_keyboard_interrupt_while_the_failure_is_reported_ends_the_turn_cancelled():
    """Baseline regression, O3: today ``failed``/``llm`` is published and ``loop.error`` is set.

    Driven by a receiver that raises ``KeyboardInterrupt`` while a provider failure is reported.
    ``run()`` is awaited directly inside ``pytest.raises`` (premises: the interrupt still
    propagates, and the receiver saw no outcome yet). After: the outcome is ``cancelled`` with no
    stage or message, ``reported`` False and ``loop.error`` None.
    """
    seen: list[Any] = []

    def receiver(text):
        seen.append(loop.outcome)
        raise KeyboardInterrupt

    callbacks = RecordingCallbacks(raises={"on_system_message": receiver})
    loop = make_loop(ScriptedProvider([RuntimeError("boom")]), callbacks=callbacks)

    _await_run_expecting(loop, KeyboardInterrupt)

    assert seen == [None]
    assert loop.outcome == _CANCELLED
    assert loop.error is None


# -- A cancellation requested while the turn ends ------------------------------


def _self_cancelling_loop():
    """A provider failure whose receiver cancels the task that runs the turn, then returns."""

    def receiver(text):
        task = asyncio.current_task()
        assert task is not None
        task.cancel()

    callbacks = RecordingCallbacks(raises={"on_system_message": receiver})
    return make_loop(ScriptedProvider([RuntimeError("boom")]), callbacks=callbacks)


def test_a_cancellation_requested_while_the_turn_ends_ends_it_cancelled():
    """Baseline regression, O7b: the task ends cancelled but ``failed``/``llm`` is published.

    ``run()`` runs in its own task and the receiver cancels it and returns (premise: the task
    ends cancelled). After: the outcome is ``cancelled`` with no stage or message, ``reported``
    False and ``loop.error`` None.
    """
    loop = _self_cancelling_loop()

    async def go() -> bool:
        task = asyncio.create_task(loop.run())
        try:
            await task
        except asyncio.CancelledError:
            pass
        return task.cancelled()

    assert asyncio.run(go()) is True
    assert loop.outcome == _CANCELLED
    assert loop.error is None


def test_a_cancellation_requested_while_the_turn_ends_is_delivered_once():
    """Baseline regression, O7c: today ``run()`` returns, so the cancellation lands on the next await.

    A caller in the task that owns the request catches the ``CancelledError`` from ``run()``,
    calls ``uncancel()`` and awaits. After: ``run()`` raised it once, so that next await
    completes. On the parent the caller never saw a ``CancelledError`` from ``run()``, and the
    pending one is delivered at its next await instead.
    """
    loop = _self_cancelling_loop()

    async def caller() -> str:
        try:
            await loop.run()
        except asyncio.CancelledError:
            task = asyncio.current_task()
            assert task is not None
            task.uncancel()
        try:
            await asyncio.sleep(0.01)
        except asyncio.CancelledError:
            return "a second cancellation was delivered"
        return "no second delivery"

    async def go() -> str:
        try:
            return await asyncio.create_task(caller())
        except asyncio.CancelledError:
            return "task cancelled"

    assert asyncio.run(go()) == "no second delivery"


def test_a_first_sigint_while_the_failure_is_reported_ends_the_turn_cancelled(
    default_sigint_handler,
):
    """Baseline regression, O8: ``asyncio.run`` raises ``KeyboardInterrupt`` with ``failed``/``llm`` published.

    Python's default SIGINT handler is installed, so ``asyncio.run``'s own handler cancels the
    main task on the first SIGINT. The receiver raises that signal while a provider failure is
    reported (premise: ``asyncio.run`` raises ``KeyboardInterrupt``). After: the full cancelled
    state, with no stage or message, ``reported`` False and ``loop.error`` None.
    """
    assert signal.getsignal(signal.SIGINT) is signal.default_int_handler
    callbacks = RecordingCallbacks(raises={"on_system_message": lambda text: signal.raise_signal(signal.SIGINT)})
    loop = make_loop(ScriptedProvider([RuntimeError("boom")]), callbacks=callbacks)

    interrupted = False
    try:
        asyncio.run(loop.run())
    except KeyboardInterrupt:
        interrupted = True

    assert interrupted
    assert loop.outcome == _CANCELLED
    assert loop.error is None


# -- A hook that recovers a TaskGroup failure ------------------------------------


async def _recovering_hook(messages):
    """On Python 3.12.9 this leaves the task's cancel count at 1 with nothing pending."""

    async def child():
        await asyncio.sleep(0.01)
        raise ValueError("child failed")

    try:
        async with asyncio.TaskGroup() as group:
            group.create_task(child())
    except* ValueError:
        pass
    await asyncio.sleep(0)


def test_a_recovered_task_group_failure_does_not_cancel_a_completed_turn():
    """Preservation: a risen cancel count with nothing pending is not a cancellation.

    The hook recovers a ``TaskGroup`` child failure. The text reply still ends ``completed``.
    """
    loop = make_loop(ScriptedProvider([chunk(content="done")]), pre_iteration_hook=_recovering_hook)

    run_turn(loop)

    assert loop.outcome == TurnOutcome("completed")


def test_a_recovered_task_group_failure_does_not_cancel_a_failed_turn():
    """Preservation: after the same hook, a provider failure is still ``failed``/``llm``, reported."""
    loop = make_loop(ScriptedProvider([RuntimeError("boom")]), pre_iteration_hook=_recovering_hook)

    run_turn(loop)

    assert loop.outcome == TurnOutcome("failed", "llm", "Error: boom", True)


# -- A cancellation elsewhere in the turn (E15, E16) -------------------------------


@pytest.fixture
def failing_iteration_event():
    """A loguru sink with ``catch=False`` that raises on the ``iteration`` record."""

    def sink(message):
        if message.record["extra"].get("evt") == "iteration":
            raise RuntimeError("sink exploded")

    sink_id = logger.add(sink, level=0, catch=False, format="{message}")
    yield
    logger.remove(sink_id)


@pytest.mark.parametrize("where", ["batch", "hook", "prompt"])
def test_a_task_cancelled_elsewhere_still_re_raises_with_history_settled(
    where, loguru_caplog, failing_iteration_event
):
    """Preservation, E15 and E16: the cancellation re-raises, even when the iteration event raises.

    The task is cancelled while a tool runs, while the iteration hook awaits and while the
    confirmation prompt is open. The turn is ``cancelled``, each call has its one tool message,
    and the failing event is one guard warning, not a failure. Passes before and after.
    """
    release = lambda: None  # noqa: E731
    if where == "batch":
        registry = HeldRegistry()
        loop = make_loop(
            ScriptedProvider([chunk(calls=[delta("c1", "read_file", _READ)])]), registry=registry
        )
        parked = lambda: asyncio.to_thread(registry.entered.wait, WAIT)  # noqa: E731
        release = registry.release.set
        expected = {"c1": "Tool call was interrupted while running"}
    elif where == "hook":
        entered = asyncio.Event()

        async def hook(messages):
            entered.set()
            await asyncio.Event().wait()

        loop = make_loop(ScriptedProvider([chunk(content="done")]), pre_iteration_hook=hook)
        parked = entered.wait
        expected = {}
    else:
        callbacks = WaitingConfirmation()
        provider = ScriptedProvider([chunk(calls=[delta("c1", "file_editor", _WRITE)])])
        loop = make_loop(provider, callbacks=callbacks, permissions={"r"})
        parked = callbacks.asked.wait
        expected = {"c1": "Tool call was cancelled before it ran."}

    ended, _ = cancel_parked_turn(loop, parked, release=release)

    assert ended == "raised"
    assert loop.outcome == _CANCELLED
    results = {m["tool_call_id"]: m["content"] for m in tool_messages(loop)}
    assert {k: v[: len(expected[k])] for k, v in results.items()} == expected
    assert _warnings(loguru_caplog, "") == [_EVENT_WARNING]
