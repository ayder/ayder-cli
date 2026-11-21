"""``ChatLoop.outcome`` says how each turn ended (plan step 1, R1).

Each exit that returns today, and each cancellation that leaves ``run()``,
sets ``loop.outcome``. Exceptions that escape ``run()`` today still escape
(step 3 changes that), and the stream's cancellation still returns normally
(step 6 changes that), so those cases assert the outcome only.

Kind: new interface. Environment: local-faked (no network; the provider,
callbacks and registry are the fakes in ``turn_fakes``). Layer: unit.

Every case is driven by real inputs: scripted provider chunks, the callbacks'
cooperative ``is_cancelled`` flag, a callback that sets it, a registry reply, a
hook that waits, and ``asyncio.Task.cancel()`` while the turn is parked.
"""

from __future__ import annotations

import asyncio

from ayder_cli.loops.chat_loop import TurnOutcome
from tests.loops.turn_fakes import (
    HeldRegistry,
    RecordingCallbacks,
    RecordingRegistry,
    ScriptedProvider,
    Stall,
    WaitingConfirmation,
    cancel_parked_turn,
    chunk,
    delta,
    make_loop,
    run_turn,
)

WAIT = 5.0
_READ = '{"file_path": "a.py"}'
_WRITE = '{"file_path": "a.py", "operation": "write", "content": "x"}'
_CANCELLED = TurnOutcome("cancelled")


def _read_call(call_id: str = "call_1"):
    return chunk(calls=[delta(call_id, "read_file", _READ)])


# -- Exits that return -------------------------------------------------------


def test_a_text_reply_completes_the_turn():
    """New interface, local-faked, unit: E1. A text reply ends the turn ``completed``."""
    loop = make_loop(ScriptedProvider([chunk(content="done")]))

    run_turn(loop)

    assert loop.outcome == TurnOutcome("completed")
    assert loop.error is None


def test_an_escalating_tool_result_escalates_the_turn():
    """New interface, local-faked, unit: E2. A tool result that asks to escalate stops the turn.

    The outcome is ``escalated`` with no message and no error; the system message the
    loop already sent is unchanged.
    """
    provider = ScriptedProvider([_read_call()])
    registry = RecordingRegistry(results={"read_file": '{"action": "escalate"}'})
    loop = make_loop(provider, registry=registry)

    run_turn(loop)

    assert loop.outcome == TurnOutcome("escalated")
    assert loop.error is None
    assert loop.cb.system == ["⚠ Escalation requested. Activity stopped; waiting for user prompt."]
    assert provider.calls == 1


def test_the_iteration_cap_fails_the_turn_at_the_limit_stage():
    """New interface, local-faked, unit: E3. The cap ends the turn ``failed`` at ``limit``.

    The message is the text reported to the user and equals ``loop.error``.
    """
    loop = make_loop(ScriptedProvider([_read_call()]), max_iterations=2)

    run_turn(loop)

    assert loop.error is not None and loop.error.startswith("Error: stopped after 2 LLM calls")
    assert loop.outcome == TurnOutcome("failed", "limit", loop.error, True)
    assert loop.cb.system == [loop.error]


def test_an_empty_response_fails_the_turn_at_the_llm_stage():
    """New interface, local-faked, unit: E4. A stream that sends nothing ends the turn ``failed`` at ``llm``."""
    loop = make_loop(ScriptedProvider([]))

    run_turn(loop)

    assert loop.error is not None and "empty response" in loop.error
    assert loop.outcome == TurnOutcome("failed", "llm", loop.error, True)
    assert loop.cb.system == [loop.error]


def test_reasoning_with_no_answer_fails_the_turn_at_the_llm_stage():
    """New interface, local-faked, unit: E5. Reasoning-only replies past the retry limit end the turn ``failed`` at ``llm``."""
    provider = ScriptedProvider([chunk(reasoning="hmm")])
    loop = make_loop(provider)

    run_turn(loop)

    assert provider.calls == 3
    assert loop.error is not None and "only reasoning" in loop.error
    assert loop.outcome == TurnOutcome("failed", "llm", loop.error, True)
    assert loop.cb.system == [loop.error]


def test_a_provider_error_fails_the_turn_at_the_llm_stage():
    """New interface, local-faked, unit: E6. A provider that raises in the stream ends the turn ``failed`` at ``llm``."""
    loop = make_loop(ScriptedProvider([RuntimeError("boom")]))

    run_turn(loop)

    assert loop.error == "Error: boom"
    assert loop.outcome == TurnOutcome("failed", "llm", "Error: boom", True)
    assert loop.cb.system == ["Error: boom"]


# -- The cooperative cancel flag ---------------------------------------------


def test_a_cancel_flag_set_before_the_request_cancels_the_turn():
    """New interface, local-faked, unit: E9. The flag is already set when the turn starts."""
    provider = ScriptedProvider([chunk(content="never asked")])
    loop = make_loop(provider, callbacks=RecordingCallbacks(cancelled=True))

    run_turn(loop)

    assert provider.calls == 0
    assert loop.outcome == _CANCELLED
    assert loop.error is None


def test_a_cancel_flag_set_during_the_stream_cancels_the_turn():
    """New interface, local-faked, unit: E10. A display callback sets the flag while the reply streams."""
    callbacks = RecordingCallbacks()
    callbacks.raises["on_assistant_content"] = lambda text: setattr(callbacks, "cancelled", True)
    provider = ScriptedProvider([chunk(content="partial")])
    loop = make_loop(provider, callbacks=callbacks)

    run_turn(loop)

    assert provider.calls == 1
    assert loop.outcome == _CANCELLED
    assert loop.error is None


# -- Task cancellation -------------------------------------------------------


def test_a_task_cancelled_in_the_stream_ends_the_turn_cancelled():
    """New interface, local-faked, unit: E8. The task is cancelled while the stream awaits.

    Asserts the outcome only: whether ``run()`` returns or re-raises here is
    step 6's change.
    """
    stall = Stall()
    loop = make_loop(ScriptedProvider([chunk(content="partial"), stall]))

    cancel_parked_turn(loop, stall.entered.wait)

    assert loop.outcome == _CANCELLED


def test_a_task_cancelled_in_the_batch_ends_the_turn_cancelled_and_re_raises():
    """New interface, local-faked, unit: E15. The task is cancelled while a tool runs."""
    registry = HeldRegistry()
    loop = make_loop(ScriptedProvider([_read_call()]), registry=registry)

    ended, _ = cancel_parked_turn(
        loop,
        lambda: asyncio.to_thread(registry.entered.wait, WAIT),
        release=registry.release.set,
    )

    assert ended == "raised"
    assert loop.outcome == _CANCELLED


def test_a_task_cancelled_in_the_hook_ends_the_turn_cancelled_and_re_raises():
    """New interface, local-faked, unit: E16. The task is cancelled while the iteration hook awaits."""
    entered = asyncio.Event()

    async def hook(messages):
        entered.set()
        await asyncio.Event().wait()

    loop = make_loop(ScriptedProvider([chunk(content="done")]), pre_iteration_hook=hook)

    ended, _ = cancel_parked_turn(loop, entered.wait)

    assert ended == "raised"
    assert loop.outcome == _CANCELLED


def test_a_task_cancelled_at_the_confirmation_prompt_ends_the_turn_cancelled_and_re_raises():
    """New interface, local-faked, unit: E16. The task is cancelled while the confirmation prompt is open."""
    callbacks = WaitingConfirmation()
    provider = ScriptedProvider([chunk(calls=[delta("call_1", "file_editor", _WRITE)])])
    loop = make_loop(provider, callbacks=callbacks, permissions={"r"})

    ended, _ = cancel_parked_turn(loop, callbacks.asked.wait)

    assert ended == "raised"
    assert loop.outcome == _CANCELLED


# -- A reused loop -----------------------------------------------------------


def test_a_second_turn_replaces_the_first_outcome_and_none_shows_while_it_runs():
    """New interface, local-faked, unit: the TUI reuses one loop across turns.

    The first turn fails; the second completes. While the second runs, the
    outcome is None, not the first turn's.
    """
    seen_while_running: list[TurnOutcome | None] = []
    callbacks = RecordingCallbacks()
    provider = ScriptedProvider([], [chunk(content="done")])
    loop = make_loop(provider, callbacks=callbacks)
    callbacks.raises["on_thinking_start"] = lambda: seen_while_running.append(loop.outcome)

    run_turn(loop)
    first = loop.outcome
    run_turn(loop)

    assert first is not None and first.status == "failed"
    assert seen_while_running == [None, None]
    assert loop.outcome == TurnOutcome("completed")
    assert loop.error is None

