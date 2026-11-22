"""An interrupt raised at the turn's end does not skip the rest of it (fix-up 28, Codex round 2 #1, R2).

The turn's end has six steps, in this order: the closing thinking stop, the settlement of the
appended reply's unrun calls, each open item's completion, the one cleanup, the partial-reply notice
(D2) and the failure report. Every receiver call is guarded, but the guard does not catch an
interrupt (``KeyboardInterrupt``, ``SystemExit``). Step 26 made the item completions and the cleanup
survive one another's interrupt; an interrupt from the closing stop still skipped every item and the
cleanup, and one from a completion or the cleanup still skipped the notice and the failure report.

Now every step runs, in order, and the interrupt leaves ``run()`` afterwards: the later one if
several receivers raised one. The turn ends ``cancelled``, as for any interrupt there (R2). For a
failed turn the notice is the second line of the failure report; for a cancelled one it is its own
message.

Kind: baseline regression unless a docstring says preservation. Environment: local-faked (no
network; the provider and the callbacks are the fakes in ``turn_fakes``). Layer: unit.

Every case is a real input: scripted provider chunks, a provider that raises, ``Task.cancel()`` while
the stream stalls, and a receiver fake that raises an interrupt.
"""

from __future__ import annotations

import asyncio

from ayder_cli.loops.chat_loop import TurnOutcome
from tests.loops.turn_fakes import (
    PARK_TIMEOUT,
    RecordingCallbacks,
    ScriptedProvider,
    Stall,
    chunk,
    delta,
    escape,
    make_loop,
    run_turn,
)

_NOTICE = "The partial reply above was not saved."
_FAILURE = "Error: provider exploded"
_TWO_ITEMS = [delta("c1", "read_file", ""), delta("c2", "read_file", "")]
_CANCELLED = TurnOutcome("cancelled")


def _raising_on_call(number: int, exc: BaseException):
    """A receiver that raises ``exc`` on its ``number``-th call and returns on the others."""
    calls: list[int] = []

    def receiver(*_args):
        calls.append(1)
        if len(calls) == number:
            raise exc

    return receiver


def _raising_for_item(key: str, exc: BaseException):
    """An ``on_tool_complete`` receiver that raises ``exc`` for the item ``key`` only."""

    def receiver(call_id, result):
        if call_id == key:
            raise exc

    return receiver


def _attempts(loop) -> dict[str, int]:
    """How many completions the receiver was given for each item."""
    return {key: len(results) for key, results in loop.cb.completes_by_key().items()}


def _calls(loop, *names: str) -> list[str]:
    return [name for name, _ in loop.cb.of(*names)]


# -- The closing thinking stop raises an interrupt (Codex's probe 1) -------------------------------------


def _a_closing_stop_that_raises_an_interrupt(extra: dict | None = None):
    """Two items open (the first chunk names two calls), a late reasoning chunk opens a thinking
    phase, then the provider fails. The receiver of the phase's closing stop (the second stop of the
    turn) raises ``KeyboardInterrupt``."""
    interrupt = KeyboardInterrupt("closing stop")
    callbacks = RecordingCallbacks(
        raises={"on_thinking_stop": _raising_on_call(2, interrupt), **(extra or {})}
    )
    provider = ScriptedProvider(
        [chunk(calls=_TWO_ITEMS), chunk(reasoning="late"), RuntimeError("provider exploded")]
    )
    loop = make_loop(provider, callbacks=callbacks)
    return loop, interrupt, escape(run_turn, loop)


def test_an_interrupt_from_the_closing_stop_still_gives_each_open_item_its_one_completion():
    """Baseline regression, Codex round 2 #1: neither item gets a completion attempt today (R4b)."""
    loop, _, _ = _a_closing_stop_that_raises_an_interrupt()

    assert _attempts(loop) == {"c1": 1, "c2": 1}


def test_an_interrupt_from_the_closing_stop_still_gets_the_one_cleanup_attempt():
    """Baseline regression, Codex round 2 #1: the cleanup runs zero times today (R5b)."""
    loop, _, _ = _a_closing_stop_that_raises_an_interrupt()

    assert len(loop.cb.of("on_tools_cleanup")) == 1


def test_an_interrupt_from_the_closing_stop_still_reports_the_failure_once():
    """Baseline regression, Codex round 2 #1: the failure is never reported today, so the user is
    not told the turn failed (R7)."""
    loop, _, _ = _a_closing_stop_that_raises_an_interrupt()

    assert loop.cb.system == [_FAILURE]


def test_the_steps_of_the_turns_end_run_in_their_order_after_an_interrupt_from_the_closing_stop():
    """Baseline regression, Codex round 2 #1: only the stop runs today.

    The first stop closed the phase the tool-call chunk ended; the second is the one that raised.
    """
    loop, _, _ = _a_closing_stop_that_raises_an_interrupt()

    steps = _calls(loop, "on_thinking_stop", "on_tool_complete", "on_tools_cleanup", "on_system_message")
    assert steps == [
        "on_thinking_stop",
        "on_thinking_stop",
        "on_tool_complete",
        "on_tool_complete",
        "on_tools_cleanup",
        "on_system_message",
    ]


def test_the_interrupt_from_the_closing_stop_is_the_object_that_leaves_run():
    """Preservation: the receiver's own exception propagates, not a copy or a replacement."""
    _, interrupt, escaped = _a_closing_stop_that_raises_an_interrupt()

    assert escaped is interrupt


def test_a_turn_that_ended_with_an_interrupt_from_the_closing_stop_is_cancelled():
    """Preservation (R2): the failure was reported, and the turn still ends ``cancelled``."""
    loop, _, _ = _a_closing_stop_that_raises_an_interrupt()

    assert loop.outcome == _CANCELLED


# -- An item's completion raises an interrupt after visible text (Codex's probe 2) ------------------------


def _a_completion_that_raises_an_interrupt_after_visible_text(receiver_name: str = "on_tool_complete"):
    """Visible text and two items in the first chunk, then the provider fails. The receiver of the
    first item's completion (or the cleanup, when ``receiver_name`` says so) raises
    ``KeyboardInterrupt``."""
    interrupt = KeyboardInterrupt("first")
    if receiver_name == "on_tool_complete":
        receiver = _raising_for_item("c1", interrupt)
    else:
        receiver = _raising_on_call(1, interrupt)
    callbacks = RecordingCallbacks(raises={receiver_name: receiver})
    provider = ScriptedProvider(
        [chunk(content="partial text", calls=_TWO_ITEMS), RuntimeError("provider exploded")]
    )
    loop = make_loop(provider, callbacks=callbacks)
    return loop, interrupt, escape(run_turn, loop)


def test_an_interrupt_from_an_items_completion_still_tells_the_user_the_partial_reply_was_lost():
    """Baseline regression, Codex round 2 #1 (D2): no system message mentions it today."""
    loop, _, _ = _a_completion_that_raises_an_interrupt_after_visible_text()

    assert len([text for text in loop.cb.system if _NOTICE in text]) == 1


def test_that_notice_is_the_second_line_of_the_one_failure_report():
    """Baseline regression, Codex round 2 #1: the notice rewrites a failed decision's message before
    the report delivers it, so the order of the two steps still holds."""
    loop, _, _ = _a_completion_that_raises_an_interrupt_after_visible_text()

    assert loop.cb.system == [f"{_FAILURE}\n{_NOTICE}"]


def test_an_interrupt_from_the_cleanup_still_tells_the_user_the_partial_reply_was_lost():
    """Baseline regression, Codex round 2 #1: the cleanup is the last receiver before the notice."""
    loop, _, _ = _a_completion_that_raises_an_interrupt_after_visible_text("on_tools_cleanup")

    assert loop.cb.system == [f"{_FAILURE}\n{_NOTICE}"]


def test_the_interrupt_from_an_items_completion_is_the_object_that_leaves_run():
    """Preservation: the receiver's own exception propagates."""
    _, interrupt, escaped = _a_completion_that_raises_an_interrupt_after_visible_text()

    assert escaped is interrupt


def test_a_turn_that_ended_with_an_interrupt_from_an_items_completion_is_cancelled():
    """Preservation (R2): the notice and the report were delivered, and the turn ends ``cancelled``."""
    loop, _, _ = _a_completion_that_raises_an_interrupt_after_visible_text()

    assert loop.outcome == _CANCELLED


# -- A cancelled turn: the notice is its own message -------------------------------------------------------


def _cancelled_after_visible_text_with_an_interrupt_from_an_items_completion():
    """The task is cancelled while the stream waits, after visible text and two items. The receiver of
    the first item's completion raises ``KeyboardInterrupt`` while the turn's end runs."""
    interrupt = KeyboardInterrupt("first")
    callbacks = RecordingCallbacks(raises={"on_tool_complete": _raising_for_item("c1", interrupt)})
    stall = Stall()
    provider = ScriptedProvider([chunk(content="partial text", calls=_TWO_ITEMS), stall])
    loop = make_loop(provider, callbacks=callbacks)

    async def main():
        task = asyncio.create_task(loop.run())
        await asyncio.wait_for(stall.entered.wait(), PARK_TIMEOUT)
        task.cancel()
        await task

    return loop, interrupt, escape(asyncio.run, main())


def test_a_cancelled_turn_still_sends_the_notice_as_its_own_message_after_an_interrupt():
    """Baseline regression, Codex round 2 #1 (D2): a cancellation sends no failure report, so the
    notice is a system message of its own, and it is not sent today."""
    loop, _, _ = _cancelled_after_visible_text_with_an_interrupt_from_an_items_completion()

    assert loop.cb.system == [_NOTICE]


def test_the_interrupt_that_ended_a_cancelled_turn_is_the_object_that_leaves_run():
    """Preservation: the interrupt replaces the cancellation, as any exception raised while the turn
    ends does."""
    _, interrupt, escaped = _cancelled_after_visible_text_with_an_interrupt_from_an_items_completion()

    assert escaped is interrupt


# -- Several receivers raise an interrupt: the later one leaves run() ---------------------------------------


def test_with_two_interrupts_the_later_one_leaves_run_and_the_outcome_is_cancelled():
    """Baseline regression, Codex round 2 #1: the first interrupt ends the turn's end today, so the
    second receiver is never reached and the first leaves ``run()``.

    The closing stop raises one interrupt and the first item's completion another. After: both are
    raised, and the later one propagates (the rule the plan records).
    """
    first, second = KeyboardInterrupt("closing stop"), KeyboardInterrupt("completion")
    callbacks = RecordingCallbacks(
        raises={
            "on_thinking_stop": _raising_on_call(2, first),
            "on_tool_complete": _raising_for_item("c1", second),
        }
    )
    provider = ScriptedProvider(
        [chunk(calls=_TWO_ITEMS), chunk(reasoning="late"), RuntimeError("provider exploded")]
    )
    loop = make_loop(provider, callbacks=callbacks)

    escaped = escape(run_turn, loop)

    assert escaped is second
    assert loop.outcome == _CANCELLED
