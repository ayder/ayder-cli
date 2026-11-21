"""A complete reply is recorded before the loop's own telemetry can fail it (fix-up 23, Codex #2).

Spec R3b: a complete reply is appended to history, and its calls are held for settlement, before
anything that can fail. The loop emitted a ``tool_call_received`` event for each call before it
appended the reply. An event sink that raises (loguru's ``catch=False``) therefore discarded a
reply the provider had finished: only the system and user messages remained, and the user was told
the reply was partial. Now the reply and its settlement obligations come first. The event is the
loop's own code, so a raising sink still fails the turn as ``failed``/``internal`` (R7c); but the
reply is in history, its call is settled with the failure text, and no partial-reply notice is added.

Kind: baseline regression unless a docstring says preservation. Environment: local-faked (no
network; the provider, callbacks and registry are the fakes in ``turn_fakes``). Layer: unit.

The failing sink is the third-party seam, as in the iteration-event tests: a loguru sink with
``catch=False`` that raises on one record, added and removed around the turn.
"""

from __future__ import annotations

import pytest
from loguru import logger

from tests.loops.turn_fakes import (
    ScriptedProvider,
    chunk,
    delta,
    escape,
    make_loop,
    run_turn,
    tool_messages,
)

_READ = '{"file_path": "a.py"}'
_REPLY_TEXT = "Let me read the file. "
_FAILURE_TEXT = "Tool call was not run because the turn failed."
_PARTIAL_NOTICE = "The partial reply above was not saved."


def _a_finished_reply_with_text_and_one_call_while_the_event_sink_fails():
    """The provider finishes normally with assistant text and one call; a sink that raises on the
    ``tool_call_received`` record only is installed for the turn."""

    def sink(message):
        if message.record["extra"].get("evt") == "tool_call_received":
            raise RuntimeError("sink exploded")

    sink_id = logger.add(sink, level=0, catch=False, format="{message}")
    try:
        provider = ScriptedProvider([chunk(content=_REPLY_TEXT, calls=[delta("c1", "read_file", _READ)])])
        loop = make_loop(provider)
        escaped = escape(run_turn, loop)
    finally:
        logger.remove(sink_id)
    return loop, escaped


@pytest.mark.allows_internal_turn_failure
def test_the_finished_reply_is_in_history_when_the_event_sink_fails():
    """Baseline regression, Codex #2: only the system and user messages remain today."""
    loop, _ = _a_finished_reply_with_text_and_one_call_while_the_event_sink_fails()

    replies = [m for m in loop.messages if m["role"] == "assistant"]
    assert [m["content"] for m in replies] == [_REPLY_TEXT]


@pytest.mark.allows_internal_turn_failure
def test_the_reply_keeps_its_call_in_history_when_the_event_sink_fails():
    """Baseline regression, Codex #2: the call is not recorded with the reply today."""
    loop, _ = _a_finished_reply_with_text_and_one_call_while_the_event_sink_fails()

    calls = [c["id"] for m in loop.messages if m["role"] == "assistant" for c in m.get("tool_calls", [])]
    assert calls == ["c1"]


@pytest.mark.allows_internal_turn_failure
def test_the_calls_of_the_finished_reply_get_the_failure_text_when_the_event_sink_fails():
    """Baseline regression, Codex #2 (R3b): the call has no tool message today.

    After: the turn's end settles it with the not-run text for a failed turn.
    """
    loop, _ = _a_finished_reply_with_text_and_one_call_while_the_event_sink_fails()

    assert {m["tool_call_id"]: m["content"] for m in tool_messages(loop)} == {"c1": _FAILURE_TEXT}


@pytest.mark.allows_internal_turn_failure
def test_no_partial_reply_notice_is_added_when_the_reply_was_saved():
    """Baseline regression, Codex #2 (D2): the user is told the reply was partial today.

    The text was shown and the reply is now saved, so the notice would be false.
    """
    loop, _ = _a_finished_reply_with_text_and_one_call_while_the_event_sink_fails()

    assert _PARTIAL_NOTICE not in (loop.outcome.message or "")
    assert not [text for text in loop.cb.system if _PARTIAL_NOTICE in text]


@pytest.mark.allows_internal_turn_failure
def test_a_failing_event_sink_still_fails_the_turn_as_internal_and_escapes_nothing():
    """Preservation (R7c): the event is the loop's own code, so the failure is ``internal``.

    Holds today, and after: only the order of the reply and the event changes.
    """
    loop, escaped = _a_finished_reply_with_text_and_one_call_while_the_event_sink_fails()

    assert escaped is None
    assert (loop.outcome.status, loop.outcome.stage) == ("failed", "internal")


def test_a_normal_turn_emits_one_tool_call_received_event_per_call(loguru_caplog):
    """Preservation (R12): each assembled call is recorded once, with its id and argument size."""
    provider = ScriptedProvider(
        [chunk(calls=[delta("c1", "read_file", _READ), delta("c2", "read_file", '{"file_path": "bb.py"}')])],
        [chunk(content="done")],
    )
    loop = make_loop(provider)
    run_turn(loop)

    received = [
        (r["extra"]["call_id"], r["extra"]["arg_chars"])
        for r in loguru_caplog.records
        if r["extra"].get("evt") == "tool_call_received"
    ]
    assert received == [("c1", len(_READ)), ("c2", len('{"file_path": "bb.py"}'))]
