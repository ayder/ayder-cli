"""Every tool item the loop opened ends finished, and the cleanup runs once (plan step 16).

The chat shows one item per tool call. The loop opened items while it streamed a reply and in the
tool batch, and finished them only on the batch's normal path. A turn that ended any other way left
its running items running forever (P1 F12e): a cancelled task (E15), a provider that raised after the
call was announced (E6), a cancel flag set after the reply (E10), a receiver that raised for one call
(E14). The activity bar's cleanup was skipped with them.

Now the loop tracks the items it opened. Settlement publishes each call it handled (its recorded
result with that result's status, ``interrupted``, or ``not_run`` with the cancel text), and the
turn's end finishes every open item once, through the guard: a call that never reached a batch gets
``not_run`` with the cancel text on a cancellation and the failure text on a failure. ``on_tools_cleanup``
is attempted once on that abnormal exit, and only when items opened since the last cleanup. A receiver
that raised for an item is not called again for it.

Kind: baseline regression unless a docstring says preservation. Environment: local-faked (no network;
the provider, registry and callbacks are the fakes in ``turn_fakes``; the policy case runs the real
registry with a real middleware). Layer: unit.

The item a receiver sees finished is the key it was opened under; the status is the one the loop
reports with the text (``on_tool_complete`` receives a ``ToolResultText``).
"""

from __future__ import annotations

import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from loguru import logger

from tests.loops.turn_fakes import (
    PARK_TIMEOUT,
    HeldRegistry,
    RecordingCallbacks,
    ScriptedProvider,
    chunk,
    delta,
    escape,
    make_loop,
    run_turn,
)

_A = '{"file_path": "a.py"}'
_B = '{"file_path": "b.py"}'
_C = '{"file_path": "c.py"}'

_CANCEL_TEXT = "Tool call was cancelled before it ran."
_FAILURE_TEXT = "Tool call was not run because the turn failed."
_INTERRUPTED_TEXT = (
    "Tool call was interrupted while running and may have partially applied. "
    "Check the current state before retrying."
)


# -- Helpers -------------------------------------------------------------------------------------


def _finish_of(loop, key):
    """The last ``(status, text)`` the receiver was given for the item ``key``, or None."""
    results = loop.cb.completes_by_key().get(key)
    if not results:
        return None
    last = results[-1]
    return getattr(last, "status", None), str(last)


def _status_of(loop, key):
    """The status the receiver was last given for the item ``key``, or None."""
    finish = _finish_of(loop, key)
    return None if finish is None else finish[0]


def _text_of(loop, key):
    """The text the receiver was last given for the item ``key``, or None."""
    finish = _finish_of(loop, key)
    return None if finish is None else finish[1]


def _cleanups(loop) -> int:
    return len(loop.cb.of("on_tools_cleanup"))


async def _until(event: threading.Event) -> None:
    deadline = time.monotonic() + PARK_TIMEOUT
    while not event.is_set():
        assert time.monotonic() < deadline, "timed out waiting for a worker"
        await asyncio.sleep(0.005)


def _run_cancelled(loop, parked, release=lambda: None, *, workers: int | None = None) -> None:
    """Run a turn as a task and cancel it once ``parked`` returns, as Ctrl+C does.

    ``workers`` limits the thread pool, so the calls after the first wait in its queue.
    """

    async def main() -> None:
        if workers is not None:
            asyncio.get_running_loop().set_default_executor(ThreadPoolExecutor(max_workers=workers))
        task = asyncio.create_task(loop.run())
        await asyncio.wait_for(parked(), PARK_TIMEOUT)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        finally:
            release()

    asyncio.run(main())


def _a_running_call(*deltas):
    """A turn parked at a tool that runs until released; returns the loop and its registry."""
    registry = HeldRegistry()
    loop = make_loop(ScriptedProvider([chunk(calls=list(deltas))]), registry=registry)
    return loop, registry


# -- E15: the task is cancelled while a parallel call runs -------------------------------------


def test_a_cancelled_turn_finishes_the_item_of_the_call_that_was_running():
    """Baseline regression, E15 (P1 F12e): the item stays running today."""
    loop, registry = _a_running_call(delta("c1", "read_file", _A))

    _run_cancelled(loop, lambda: _until(registry.entered), registry.release.set)

    assert _finish_of(loop, "c1") == ("interrupted", _INTERRUPTED_TEXT)


def test_a_cancelled_turn_runs_the_cleanup_once():
    """Baseline regression, E15: the cleanup is skipped with the items today."""
    loop, registry = _a_running_call(delta("c1", "read_file", _A))

    _run_cancelled(loop, lambda: _until(registry.entered), registry.release.set)

    assert _cleanups(loop) == 1


def test_a_started_call_and_a_queued_call_are_finished_with_their_own_statuses():
    """Baseline regression: neither item is finished today.

    Two calls share a thread pool of one worker, so the second waits behind the first, which is
    held. The task is cancelled while the first runs.
    """
    loop, registry = _a_running_call(delta("c1", "read_file", _A), delta("c2", "read_file", _B))

    _run_cancelled(loop, lambda: _until(registry.entered), registry.release.set, workers=1)

    assert (_status_of(loop, "c1"), _status_of(loop, "c2")) == ("interrupted", "not_run")


def test_a_started_call_and_a_queued_call_are_finished_with_the_texts_settlement_gave_history():
    """Baseline regression: as above, the item text is the text in history."""
    loop, registry = _a_running_call(delta("c1", "read_file", _A), delta("c2", "read_file", _B))

    _run_cancelled(loop, lambda: _until(registry.entered), registry.release.set, workers=1)

    assert (_text_of(loop, "c1"), _text_of(loop, "c2")) == (_INTERRUPTED_TEXT, _CANCEL_TEXT)


# -- E6: the provider raises after a call was announced ----------------------------------------------


def _the_provider_raises_after_a_call_was_announced():
    provider = ScriptedProvider(
        [chunk(calls=[delta("c1", "read_file", "")]), RuntimeError("provider exploded")]
    )
    return make_loop(provider)


def test_an_item_opened_while_streaming_is_finished_when_the_provider_raises():
    """Baseline regression, E6: the item stays running today.

    Driven by a reply whose first chunk names a call and whose stream then raises. The call never
    reached a batch, so its item is ``not_run`` with the failure text.
    """
    loop = _the_provider_raises_after_a_call_was_announced()
    run_turn(loop)

    assert _finish_of(loop, "c1") == ("not_run", _FAILURE_TEXT)


def test_a_turn_that_failed_with_an_item_open_runs_the_cleanup_once():
    """Baseline regression, E6: no cleanup is attempted today."""
    loop = _the_provider_raises_after_a_call_was_announced()
    run_turn(loop)

    assert _cleanups(loop) == 1


# -- E10: the cancel flag is set after a tool-call reply -----------------------------------------


def _the_flag_is_set_after_a_tool_call_reply():
    callbacks = RecordingCallbacks()
    callbacks.raises["on_tool_start"] = lambda *args: setattr(callbacks, "cancelled", True)
    provider = ScriptedProvider([chunk(calls=[delta("c1", "read_file", _A)])])
    return make_loop(provider, callbacks=callbacks)


def test_an_item_whose_call_was_cancelled_before_the_batch_is_finished_as_not_run():
    """Baseline regression, E10: history has the cancel text (step 8) but the item stays running."""
    loop = _the_flag_is_set_after_a_tool_call_reply()
    run_turn(loop)

    assert _finish_of(loop, "c1") == ("not_run", _CANCEL_TEXT)


# -- E14: on_tool_complete raises for the first of three calls -------------------------------------


def _complete_raises_for_the_first_of_three_calls():
    def raise_for_c1(call_id, result):
        if call_id == "c1":
            raise RuntimeError("ui exploded")

    callbacks = RecordingCallbacks(raises={"on_tool_complete": raise_for_c1})
    provider = ScriptedProvider(
        [chunk(calls=[delta("c1", "read_file", _A), delta("c2", "read_file", _B), delta("c3", "read_file", _C)])]
    )
    return make_loop(provider, callbacks=callbacks)


def _run_with_one_worker(loop) -> None:
    """One worker runs the calls in order, so ``c1`` is the first to complete."""

    async def main() -> None:
        asyncio.get_running_loop().set_default_executor(ThreadPoolExecutor(max_workers=1))
        await asyncio.wait_for(loop.run(), PARK_TIMEOUT)

    asyncio.run(main())


def test_the_other_items_are_finished_when_the_receiver_raised_for_the_first():
    """Baseline regression, E14: the collector stops at the raise, so ``c2`` and ``c3`` stay running."""
    loop = _complete_raises_for_the_first_of_three_calls()
    _run_with_one_worker(loop)

    assert set(loop.cb.completes_by_key()) == {"c1", "c2", "c3"}


def test_a_receiver_that_raised_for_an_item_is_not_called_again_for_it():
    """Preservation, E14: one attempt per item. Holds today, because nothing finishes it again."""
    loop = _complete_raises_for_the_first_of_three_calls()
    _run_with_one_worker(loop)

    assert len(loop.cb.completes_by_key()["c1"]) == 1


def test_a_receiver_that_raised_for_an_item_leaves_the_cleanup_attempted_once():
    """Baseline regression, E14: no cleanup is attempted today."""
    loop = _complete_raises_for_the_first_of_three_calls()
    _run_with_one_worker(loop)

    assert _cleanups(loop) == 1


def test_a_receiver_that_raised_for_an_item_keeps_the_outcome_failed_in_the_ui():
    """Preservation, E14: finishing the other items does not change the turn's outcome."""
    loop = _complete_raises_for_the_first_of_three_calls()
    _run_with_one_worker(loop)

    assert (loop.outcome.status, loop.outcome.stage) == ("failed", "ui")


# -- The cleanup is attempted once ------------------------------------------------------------------


def test_a_cleanup_that_raised_is_not_called_again():
    """Preservation, E14: the abnormal-exit cleanup must not retry the receiver that raised.

    The batch's own cleanup raises; the turn fails in the UI with no item open since, so the turn's
    end does not call it again. Holds today (there is no abnormal-exit cleanup yet).
    """
    callbacks = RecordingCallbacks(raises={"on_tools_cleanup": RuntimeError("cleanup exploded")})
    loop = make_loop(ScriptedProvider([chunk(calls=[delta("c1", "read_file", _A)])]), callbacks=callbacks)
    run_turn(loop)

    assert (_cleanups(loop), loop.outcome.stage) == (1, "ui")


def test_a_normal_batch_makes_exactly_one_cleanup_and_finishes_its_items_once():
    """Preservation: the per-batch cleanup stays, and the turn's end adds nothing after it."""
    loop = make_loop(
        ScriptedProvider([chunk(calls=[delta("c1", "read_file", _A)])], [chunk(content="done")])
    )
    run_turn(loop)

    assert (_cleanups(loop), len(loop.cb.completes_by_key()["c1"])) == (1, 1)


# -- Late workers never call the UI ----------------------------------------------------------------


def test_a_worker_that_finishes_after_the_turn_ended_calls_no_callback():
    """Preservation: a late worker of a cancelled batch writes nothing and reaches no receiver."""
    loop, registry = _a_running_call(delta("c1", "read_file", _A))
    seen: list[int] = []

    async def main() -> None:
        task = asyncio.create_task(loop.run())
        await asyncio.wait_for(_until(registry.entered), PARK_TIMEOUT)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        seen.append(len(loop.cb.calls))
        registry.release.set()
        await asyncio.sleep(0.3)  # the late worker finishes

    asyncio.run(main())

    assert len(loop.cb.calls) == seen[0]


# -- A recorded policy failure that the collector never read --------------------------------------------


class _PolicyRaisesForA:
    """A real middleware: the call for ``a.txt`` is held, then blocked by policy; others pass."""

    def __init__(self) -> None:
        self.release = threading.Event()

    def __call__(self, tool_name, args):
        if str(args.get("file_path", "")).endswith("a.txt"):  # the registry hands over an absolute path
            self.release.wait(PARK_TIMEOUT)
            raise PermissionError(f"blocked by policy middleware: {tool_name}")


def _cancelled_after_a_policy_failure_was_recorded(tmp_path):
    """Parallel calls A and B; B returns first.

    B's completion releases A's policy, which raises, then waits for the worker's ``tool_call``
    event (emitted right after the failure is recorded) and cancels the task, so the collector
    never reads A. The event is seen through a Loguru sink, so no code of the loop is touched.
    """
    from ayder_cli.core.context import ProjectContext
    from ayder_cli.tools.registry import create_default_registry

    (tmp_path / "a.txt").write_text("a\n")
    (tmp_path / "b.txt").write_text("b\n")
    middleware = _PolicyRaisesForA()
    registry = create_default_registry(ProjectContext(str(tmp_path)))
    registry.add_middleware(middleware)

    failure_recorded = threading.Event()

    def watch_for_the_failed_call(message) -> None:
        extra = message.record["extra"]
        if extra.get("evt") == "tool_call" and extra.get("ok") is False:
            failure_recorded.set()

    def on_complete(call_id, result):
        if call_id != "B":
            return
        middleware.release.set()
        if not failure_recorded.wait(PARK_TIMEOUT):
            raise RuntimeError("the worker never recorded the failure")
        asyncio.current_task().cancel()

    callbacks = RecordingCallbacks(raises={"on_tool_complete": on_complete})
    calls = [
        delta("A", "read_file", '{"file_path": "a.txt"}'),
        delta("B", "read_file", '{"file_path": "b.txt"}'),
    ]
    loop = make_loop(ScriptedProvider([chunk(calls=calls)]), registry=registry, callbacks=callbacks)

    async def main() -> None:
        task = asyncio.create_task(loop.run())
        try:
            await task
        except asyncio.CancelledError:
            pass

    sink_id = logger.add(watch_for_the_failed_call, level=0, format="{message}", catch=False)
    try:
        asyncio.run(main())
    finally:
        logger.remove(sink_id)
    return loop


def test_a_call_whose_policy_raised_and_was_recorded_is_finished_with_the_status_error(tmp_path):
    """Baseline regression: the item stays running today."""
    loop = _cancelled_after_a_policy_failure_was_recorded(tmp_path)

    assert _status_of(loop, "A") == "error"


def test_the_item_of_a_recorded_policy_failure_shows_the_recorded_text(tmp_path):
    """Baseline regression: as above; the text is the recorded ``Error: ...``, not a guess."""
    loop = _cancelled_after_a_policy_failure_was_recorded(tmp_path)

    text = _text_of(loop, "A") or ""
    assert text.startswith("Error") and "blocked by policy middleware" in text


# -- An interrupt while one item is finished (fix-up 26, Codex #8) ----------------------------------------


def _the_first_completion_receiver_raises_an_interrupt():
    """Codex's probe: two items are open (the first chunk names two calls), the provider then fails
    mid-stream, and the receiver of the first item's completion raises ``KeyboardInterrupt``."""
    interrupt = KeyboardInterrupt("first")

    def raise_for_c1(call_id, result):
        if call_id == "c1":
            raise interrupt

    callbacks = RecordingCallbacks(raises={"on_tool_complete": raise_for_c1})
    provider = ScriptedProvider(
        [chunk(calls=[delta("c1", "read_file", ""), delta("c2", "read_file", "")]),
         RuntimeError("provider exploded")]
    )
    loop = make_loop(provider, callbacks=callbacks)
    return loop, interrupt, escape(run_turn, loop)


def test_an_interrupt_from_one_items_completion_does_not_strand_the_other_items():
    """Baseline regression, Codex #8: the interrupt skips the second item's attempt today (R4b)."""
    loop, _, _ = _the_first_completion_receiver_raises_an_interrupt()

    assert "c2" in loop.cb.completes_by_key()


def test_an_interrupt_from_one_items_completion_still_gets_the_one_cleanup_attempt():
    """Baseline regression, Codex #8: the cleanup is never attempted today (R5b)."""
    loop, _, _ = _the_first_completion_receiver_raises_an_interrupt()

    assert _cleanups(loop) == 1


def test_the_first_interrupt_leaves_run_unchanged():
    """Preservation: the interrupt that the receiver raised is the one that leaves ``run()``."""
    _, interrupt, escaped = _the_first_completion_receiver_raises_an_interrupt()

    assert escaped is interrupt


def test_a_turn_that_ended_with_an_interrupt_is_cancelled():
    """Preservation: the outcome is ``cancelled`` (R2)."""
    loop, _, _ = _the_first_completion_receiver_raises_an_interrupt()

    assert loop.outcome.status == "cancelled"


def test_the_receiver_that_raised_the_interrupt_is_not_called_again_for_its_item():
    """Preservation: one attempt per item."""
    loop, _, _ = _the_first_completion_receiver_raises_an_interrupt()

    assert len(loop.cb.completes_by_key()["c1"]) == 1


# -- A refusal keeps its status through settlement (fix-up 27, Codex #10) --------------------------------------
#
# Unknown name, unattributed, argument refusal and missing arguments are refused before the batch
# runs anything. Each is recorded, then shown running and finished with the status ``error``. When the
# running display is what raises, the item is already open and the finish never ran, so the turn's end
# finishes it with what settlement published for the call. The record held no status, so the receiver
# was given a plain string. The probes below make the receiver raise at the start the batch shows.


def _raising_at_start_number(key, number):
    """A receiver of ``on_tool_start`` that raises on the ``number``-th start of the item ``key``."""
    starts = []

    def receiver(call_id, name, arguments):
        if call_id == key:
            starts.append(arguments)
            if len(starts) == number:
                raise RuntimeError("running preview exploded")

    return receiver


def _a_refused_call_whose_running_preview_raises(delta_of_the_call, *, start_number, key="c1"):
    """One reply with the call; the receiver raises at the batch's start of its item.

    A call with a name is announced while the reply streams (its first start), so the batch's start is
    the second one; a call without a name is not announced, so the batch's start is the first.
    """
    receiver = _raising_at_start_number(key, start_number)
    callbacks = RecordingCallbacks(raises={"on_tool_start": receiver})
    loop = make_loop(ScriptedProvider([chunk(calls=[delta_of_the_call])]), callbacks=callbacks)
    run_turn(loop)
    return loop


def test_a_call_with_missing_arguments_is_finished_with_the_status_error_when_its_preview_raises():
    """Baseline regression, Codex #10: ``read_file({})``. The item is finished with a plain string
    today, so the receiver never learns the call was an error (R4a, R4c)."""
    loop = _a_refused_call_whose_running_preview_raises(delta("c1", "read_file", "{}"), start_number=2)

    assert _status_of(loop, "c1") == "error"


def test_a_call_with_a_missing_name_is_finished_with_the_status_error_when_its_preview_raises():
    """Baseline regression, Codex #10: a call with no name, refused as unknown."""
    loop = _a_refused_call_whose_running_preview_raises(delta("c1", "", "{}"), start_number=1)

    assert _status_of(loop, "c1") == "error"


def test_a_call_with_arguments_that_are_not_an_object_is_finished_with_the_status_error_when_its_preview_raises():
    """Baseline regression, Codex #10: arguments that decode to a list are refused (F11)."""
    loop = _a_refused_call_whose_running_preview_raises(delta("c1", "read_file", "[1, 2]"), start_number=2)

    assert _status_of(loop, "c1") == "error"


def test_an_unattributed_call_is_finished_with_the_status_error_when_its_preview_raises(probe_tool):
    """Baseline regression, Codex #10: two calls started and a fragment that belongs to neither, so
    both are refused (R9b). The receiver raises at the first call's batch start."""
    probe_tool("opt_a")
    probe_tool("opt_b")
    receiver = _raising_at_start_number("a1", 2)
    callbacks = RecordingCallbacks(raises={"on_tool_start": receiver})
    provider = ScriptedProvider(
        [chunk(calls=[delta("a1", "opt_a", ""), delta("b1", "opt_b", ""), delta("", "", '{"x": 1}')])]
    )
    loop = make_loop(provider, callbacks=callbacks)
    run_turn(loop)

    assert _status_of(loop, "a1") == "error"


def test_the_text_a_refused_item_is_finished_with_is_the_refusal_the_history_holds():
    """Preservation: the status is added; the text is what it was, and it is the text in history."""
    loop = _a_refused_call_whose_running_preview_raises(delta("c1", "read_file", "{}"), start_number=2)

    history = [m["content"] for m in loop.messages if m["role"] == "tool"]
    assert history == [_text_of(loop, "c1")]
    assert history[0].startswith("Error: tool call 'read_file' has missing required arguments")


def test_every_refusal_stays_a_plain_tool_message_in_history(probe_tool):
    """Preservation (R12): the status is for the receiver. History keeps four keys and a plain ``str``,
    for each kind of refusal and for a denied call."""
    probe_tool("opt_a")
    callbacks = RecordingCallbacks(confirm="deny")
    provider = ScriptedProvider(
        [
            chunk(
                calls=[
                    delta("c1", "", "{}"),
                    delta("c2", "read_file", "[1, 2]"),
                    delta("c3", "read_file", "{}"),
                    delta("c4", "file_editor", '{"file_path": "a.py", "operation": "write", "content": "x"}'),
                ]
            )
        ],
        [chunk(content="done")],
    )
    loop = make_loop(provider, callbacks=callbacks, permissions={"r"})
    run_turn(loop)

    tool_messages = [m for m in loop.messages if m["role"] == "tool"]
    assert [sorted(m) for m in tool_messages] == [["content", "name", "role", "tool_call_id"]] * 4
    assert [type(m["content"]) for m in tool_messages] == [str] * 4
