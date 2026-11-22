"""The lost partial reply is announced (plan step 10, R3c, D2).

A reply that is not complete is not recorded and nothing from it runs; that does not change. After
partial output (at least one content chunk delivered to ``on_assistant_content`` in the iteration)
the user is now told so, once: on a failure the message gets a second line, "The partial reply
above was not saved."; on a cancellation the line is its own system message. A reply that was
saved, a failure before any content, and reasoning alone get no notice.

Kind: baseline regression unless a docstring says preservation. Environment: local-faked (no
network; the provider and callbacks are the fakes in ``turn_fakes``). Layer: unit.

Every case is a real input: scripted provider chunks, a provider that raises, and
``Task.cancel()`` while the stream awaits.
"""

from __future__ import annotations

from ayder_cli.loops.chat_loop import TurnOutcome
from tests.loops.turn_fakes import (
    RecordingCallbacks,
    ScriptedProvider,
    Stall,
    cancel_parked_turn,
    chunk,
    delta,
    make_loop,
    run_turn,
)

NOTICE = "The partial reply above was not saved."


def _original_history(loop) -> list[dict]:
    return [{"role": "system", "content": "sys"}, {"role": "user", "content": "go"}]


def _failed_after_content():
    loop = make_loop(ScriptedProvider([chunk(content="partial"), RuntimeError("boom")]))
    run_turn(loop)
    return loop


def _cancelled_after_content():
    stall = Stall()
    loop = make_loop(ScriptedProvider([chunk(content="partial"), stall]))
    ended, _ = cancel_parked_turn(loop, stall.entered.wait)
    return loop, ended


# -- After partial output (red) ---------------------------------------------------


def test_a_provider_error_after_content_ends_the_failure_message_with_the_notice():
    """Baseline regression, D2: today the message is only ``Error: boom``.

    Driven by one content chunk and then a provider error. After: the outcome's message, which is
    ``loop.error``, has the notice as its second line.
    """
    loop = _failed_after_content()

    assert loop.outcome is not None
    assert loop.outcome.message == f"Error: boom\n{NOTICE}"


def test_the_reported_failure_shows_the_notice():
    """Baseline regression, D2: the message the receiver is told is only ``Error: boom`` today."""
    loop = _failed_after_content()

    assert loop.cb.system == [f"Error: boom\n{NOTICE}"]


def test_a_cancellation_after_content_sends_one_notice_as_its_own_system_message():
    """Baseline regression, D2: nothing tells the user today.

    Driven by one content chunk and then ``Task.cancel()`` while the stream awaits. After: one
    system message, the notice.
    """
    loop, _ = _cancelled_after_content()

    assert loop.cb.system == [NOTICE]


# -- What does not change (preservation) -----------------------------------------------


def test_the_lost_partial_reply_is_still_not_recorded_after_a_failure():
    """Preservation: the partial reply is not saved, so history holds only the original messages."""
    loop = _failed_after_content()

    assert loop.messages == _original_history(loop)


def test_a_cancellation_after_content_still_re_raises_and_records_nothing():
    """Preservation: the turn is cancelled and quiet, and history is unchanged.

    Whether ``run()`` re-raised was step 6's change; this pins it with the notice added.
    """
    loop, ended = _cancelled_after_content()

    assert ended == "raised"
    assert loop.outcome == TurnOutcome("cancelled")
    assert loop.error is None
    assert loop.messages == _original_history(loop)


def test_a_failure_before_any_content_has_no_notice():
    """Preservation (spec §6): ``loop.error == "Error: boom"`` holds, with nothing to announce."""
    loop = make_loop(ScriptedProvider([RuntimeError("boom")]))

    run_turn(loop)

    assert loop.error == "Error: boom"
    assert loop.cb.system == ["Error: boom"]


def test_reasoning_alone_has_no_notice_after_a_failure():
    """Preservation: reasoning output is not a partial reply."""
    loop = make_loop(ScriptedProvider([chunk(reasoning="thinking"), RuntimeError("boom")]))

    run_turn(loop)

    assert loop.error == "Error: boom"


def test_reasoning_alone_has_no_notice_after_a_cancellation():
    """Preservation: no system message follows a cancellation during reasoning."""
    stall = Stall()
    loop = make_loop(ScriptedProvider([chunk(reasoning="thinking"), stall]))

    cancel_parked_turn(loop, stall.entered.wait)

    assert loop.cb.system == []


def test_a_reply_that_was_saved_has_no_notice_when_the_turn_fails_later():
    """Preservation: the reply is in history (step 8), so nothing is announced as lost.

    ``on_token_usage`` raises after a complete text reply.
    """
    callbacks = RecordingCallbacks(raises={"on_token_usage": RuntimeError("usage exploded")})
    loop = make_loop(ScriptedProvider([chunk(content="hello")]), callbacks=callbacks)

    run_turn(loop)

    assert loop.error == "Error: the user interface failed: usage exploded"
    assert [m["content"] for m in loop.messages if m["role"] == "assistant"] == ["hello"]


def test_the_notice_is_per_iteration():
    """Preservation: content in an earlier, saved iteration does not count for a later failure.

    The first reply streams content and calls a tool; the second request fails before any content.
    """
    provider = ScriptedProvider(
        [chunk(content="working"), chunk(calls=[delta("c1", "read_file", '{"file_path": "a.py"}')])],
        [RuntimeError("boom")],
    )
    loop = make_loop(provider)

    run_turn(loop)

    assert loop.error == "Error: boom"
