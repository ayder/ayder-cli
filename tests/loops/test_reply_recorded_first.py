"""A complete reply is recorded before anything that can fail (plan step 8, R3b, R3d).

Before this step the loop appended the assistant's reply to history only after the closing
thinking stop, the cooperative cancel check and token accounting. A turn that stopped at any of
them left a reply the user had already seen missing from history, and its tool calls with no
tool message. Now a reply with content or tool calls is appended first, and each of its calls
that never reaches the batch gets a tool message: the cancel text on a cancellation, the failure
text on a failure.

Kind: baseline regression unless a docstring says preservation. Environment: local-faked (no
network; the provider, callbacks and context are the fakes in ``turn_fakes``). Layer: unit.

Every case is a real input: a callback that sets the cooperative cancel flag, a context manager
whose ``update_from_response`` raises, a callback whose ``on_token_usage`` or second
``on_thinking_stop`` raises, driven by scripted provider chunks. Each red test asserts one history
claim; the outcome each scenario already has on the parent is pinned by a preservation test.
"""

from __future__ import annotations

import pytest

from ayder_cli.loops.chat_loop import TurnOutcome
from tests.loops.turn_fakes import (
    FakeContext,
    RecordingCallbacks,
    ScriptedProvider,
    assistant_calls,
    chunk,
    delta,
    make_loop,
    run_turn,
    tool_messages,
)

_READ = '{"file_path": "a.py"}'
_CANCEL_TEXT = "Tool call was cancelled before it ran."
_FAILURE_TEXT = "Tool call was not run because the turn failed."


def _tool_texts(loop) -> dict[str, str]:
    return {m["tool_call_id"]: m["content"] for m in tool_messages(loop)}


def _assistant_contents(loop) -> list[str]:
    return [m["content"] for m in loop.messages if m["role"] == "assistant"]


def _the_flag_is_set_during_the_stream():
    """E10: a reply with one tool call, and a callback that sets the cancel flag while it streams."""
    callbacks = RecordingCallbacks()
    callbacks.raises["on_tool_start"] = lambda *args: setattr(callbacks, "cancelled", True)
    provider = ScriptedProvider([chunk(calls=[delta("c1", "read_file", _READ)])])
    return make_loop(provider, callbacks=callbacks)


def _accounting_raises_after_a_text_reply():
    """E12: ``update_from_response`` raises after a text reply that carries usage."""
    context = FakeContext(raises={"update_from_response": RuntimeError("accounting exploded")})
    provider = ScriptedProvider([chunk(content="hello", usage={"total_tokens": 5})])
    return make_loop(provider, context=context)


def _token_usage_raises_after_a_tool_call_reply():
    """E12: ``on_token_usage`` raises after a reply with one tool call."""
    callbacks = RecordingCallbacks(raises={"on_token_usage": RuntimeError("usage exploded")})
    provider = ScriptedProvider([chunk(calls=[delta("c1", "read_file", _READ)])])
    return make_loop(provider, callbacks=callbacks)


def _the_reopened_phases_stop_raises():
    """E20: content, late reasoning, a clean end; the stop that closes the reopened phase raises."""
    stops: list[int] = []

    def second_stop_raises():
        stops.append(len(stops) + 1)
        if len(stops) == 2:
            raise RuntimeError("stop exploded")

    callbacks = RecordingCallbacks(raises={"on_thinking_stop": second_stop_raises})
    provider = ScriptedProvider([chunk(content="hello"), chunk(reasoning="late")])
    return make_loop(provider, callbacks=callbacks)


# -- The reply is in history (red) -----------------------------------------------


def test_a_cancel_flag_set_during_the_stream_leaves_the_reply_in_history():
    """Baseline regression, E10: the cancel check returns before the append (P1).

    After: the reply with its one tool call is appended.
    """
    loop = _the_flag_is_set_during_the_stream()

    run_turn(loop)

    assert [call["id"] for call in assistant_calls(loop)] == ["c1"]


def test_a_cancel_flag_set_during_the_stream_gives_the_reply_its_call_the_cancel_text():
    """Baseline regression, E10: the reply's call has no tool message today.

    After: it gets the cancel text, without the repeat note or the repaired prefix.
    """
    loop = _the_flag_is_set_during_the_stream()

    run_turn(loop)

    assert _tool_texts(loop) == {"c1": _CANCEL_TEXT}


def test_accounting_that_raises_after_a_text_reply_leaves_the_reply_in_history():
    """Baseline regression, E12: the reply the user saw is missing from history (P1 F9)."""
    loop = _accounting_raises_after_a_text_reply()

    run_turn(loop)

    assert _assistant_contents(loop) == ["hello"]


def test_a_token_usage_callback_that_raises_leaves_the_reply_in_history():
    """Baseline regression, E12: neither the reply nor a tool message is in history today."""
    loop = _token_usage_raises_after_a_tool_call_reply()

    run_turn(loop)

    assert [call["id"] for call in assistant_calls(loop)] == ["c1"]


def test_a_token_usage_callback_that_raises_gives_the_reply_its_call_the_failure_text():
    """Baseline regression, E12: the reply's call has no tool message today.

    After: it gets the R3b failure text, "Tool call was not run because the turn failed."
    """
    loop = _token_usage_raises_after_a_tool_call_reply()

    run_turn(loop)

    assert _tool_texts(loop) == {"c1": _FAILURE_TEXT}


def test_a_closing_stop_that_raises_after_a_clean_stream_leaves_the_reply_in_history():
    """Baseline regression, E20: the stop that closes the reopened phase raises before the append."""
    loop = _the_reopened_phases_stop_raises()

    run_turn(loop)

    assert _assistant_contents(loop) == ["hello"]


# -- The outcomes these scenarios already have (preservation) -------------------


@pytest.mark.parametrize(
    ("scenario", "outcome"),
    [
        pytest.param(_the_flag_is_set_during_the_stream, TurnOutcome("cancelled"), id="E10"),
        pytest.param(
            _accounting_raises_after_a_text_reply,
            # Step 9 (D4): a raising accounting call is a guard warning, not a failure.
            TurnOutcome("completed"),
            id="E12-accounting",
        ),
        pytest.param(
            _token_usage_raises_after_a_tool_call_reply,
            TurnOutcome(
                "failed", "ui", "Error: the user interface failed: usage exploded", True
            ),
            id="E12-token-usage",
        ),
        pytest.param(
            _the_reopened_phases_stop_raises,
            TurnOutcome("failed", "ui", "Error: the user interface failed: stop exploded", True),
            id="E20",
        ),
    ],
)
def test_the_turn_keeps_its_outcome_when_the_reply_is_recorded_first(scenario, outcome):
    """Preservation: recording the reply first changes history, not how the turn ends.

    Step 3 gave each of these its outcome; step 9 changed the accounting case from
    ``failed``/``context`` to ``completed`` (the reply is still in history).
    """
    loop = scenario()

    run_turn(loop)

    assert loop.outcome == outcome
