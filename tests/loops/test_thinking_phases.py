"""Each thinking phase gets exactly one stop (plan step 7, R5a, B1).

A phase opens at ``on_thinking_start`` or at a reasoning chunk after a stop, and closes at the
first content or tool-call chunk or at the end of the stream. Before this step the stream's
``finally`` sent one more stop on every path, so a reply that had already closed its phase got a
second stop, and a stream that failed after content got one too.

Kind: baseline regression unless a docstring says preservation. Environment: local-faked (no
network; the provider and callbacks are the fakes in ``turn_fakes``). Layer: unit.

Every case is a real input: scripted provider chunks, and a provider that raises.
"""

from __future__ import annotations

from ayder_cli.loops.chat_loop import TurnOutcome
from tests.loops.turn_fakes import (
    RecordingCallbacks,
    ScriptedProvider,
    chunk,
    delta,
    make_loop,
    run_turn,
)

_PHASE_CALLBACKS = (
    "on_thinking_start",
    "on_thinking_stop",
    "on_thinking_content",
    "on_assistant_content",
)


def _phases(callbacks: RecordingCallbacks, *extra: str) -> list[str]:
    """The thinking and content callbacks, in call order, without their ``on_`` prefix."""
    return [name.removeprefix("on_") for name, _ in callbacks.of(*_PHASE_CALLBACKS, *extra)]


def test_content_then_the_end_of_the_stream_stops_thinking_once():
    """Baseline regression, P1: the phase closes at the content, and the end sends a second stop.

    Driven by one content chunk. After: one stop, before the content.
    """
    loop = make_loop(ScriptedProvider([chunk(content="hello")]))

    run_turn(loop)

    assert _phases(loop.cb) == ["thinking_start", "thinking_stop", "assistant_content"]


def test_a_stream_that_fails_after_content_stops_thinking_once():
    """Baseline regression, E6 and F5: the ``finally`` sends a second stop after the failure.

    Driven by a provider that raises after one content chunk (premise: the turn is
    ``failed``/``llm``). After: the one stop that came with the content.
    """
    loop = make_loop(ScriptedProvider([chunk(content="hello"), RuntimeError("boom")]))

    run_turn(loop)

    # Step 10 (D2): content was shown and its reply was lost, so the message says so.
    assert loop.outcome == TurnOutcome(
        "failed", "llm", "Error: boom\nThe partial reply above was not saved.", True
    )
    assert _phases(loop.cb) == ["thinking_start", "thinking_stop", "assistant_content"]


def test_a_tool_call_chunk_closes_the_phase_once_per_iteration():
    """Baseline regression, P1: a tool-call chunk closes the phase, and the end sends a second stop.

    Driven by a reply that calls a tool and a second reply with text. After: each iteration has
    one start and one stop.
    """
    provider = ScriptedProvider(
        [chunk(calls=[delta("c1", "read_file", '{"file_path": "a.py"}')])],
        [chunk(content="done")],
    )
    loop = make_loop(provider)

    run_turn(loop)

    assert _phases(loop.cb) == [
        "thinking_start",
        "thinking_stop",
        "thinking_start",
        "thinking_stop",
        "assistant_content",
    ]


def test_reasoning_after_content_opens_a_phase_that_the_end_of_the_stream_closes():
    """Preservation: reasoning, content, reasoning, end gives two stops.

    The first closes the opening phase at the content; the second closes the phase the late
    reasoning reopened. Passes before and after.
    """
    provider = ScriptedProvider(
        [chunk(reasoning="first"), chunk(content="answer"), chunk(reasoning="late")]
    )
    loop = make_loop(provider)

    run_turn(loop)

    assert _phases(loop.cb) == [
        "thinking_start",
        "thinking_content",
        "thinking_stop",
        "assistant_content",
        "thinking_content",
        "thinking_stop",
    ]


def test_a_failure_while_a_phase_is_open_closes_it_once_before_the_report():
    """Preservation: a stream that fails during reasoning still gets its one stop.

    The stop comes before the failure is reported. Passes before and after.
    """
    provider = ScriptedProvider([chunk(reasoning="thinking"), RuntimeError("boom")])
    loop = make_loop(provider)

    run_turn(loop)

    assert loop.outcome == TurnOutcome("failed", "llm", "Error: boom", True)
    assert _phases(loop.cb, "on_system_message") == [
        "thinking_start",
        "thinking_content",
        "thinking_stop",
        "system_message",
    ]
