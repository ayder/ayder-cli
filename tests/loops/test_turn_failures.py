"""Every failure becomes the turn's outcome (plan step 3, R2, R7).

Before this step an exception from a collaborator, a callback or the loop's own
code could leave ``run()``; a failure in the stream was always blamed on the
LLM; a failing closer or event could replace the failure it followed; and the
failure was reported before the outcome existed. Now no ``Exception`` leaves
``run()``: it becomes ``failed`` with the stage of the collaborator that was
active, is reported once at the turn's end, and is published once.

Kind: baseline regression unless a docstring says preservation. Environment:
local-faked (no network; the provider, callbacks, registry and context are the
fakes in ``turn_fakes``). Layer: unit.

Every case is driven by a real input: a collaborator that raises (the context
manager, the hook, the registry, a callback, the provider), a tool result the
loop's own code cannot process, or a delta whose shape the loop does not
expect. The one third-party seam is loguru: the ``emit_event`` case adds a sink
with ``catch=False`` and removes it afterwards; ``emit_event`` is not patched.
"""

from __future__ import annotations

from typing import Any

import pytest
from loguru import logger

from ayder_cli.loops.chat_loop import TurnOutcome
from tests.loops.turn_fakes import (
    FakeContext,
    RecordingCallbacks,
    RecordingRegistry,
    ScriptedProvider,
    chunk,
    delta,
    escape,
    make_loop,
    run_turn,
    tool_messages,
)

_READ = '{"file_path": "a.py"}'
_WRITE = '{"file_path": "a.py", "operation": "write", "content": "x"}'
_GUARD_WARNING = "raised; continuing without it"
_FALLBACK_TEXT = "Error: the turn failed, and its error could not be described."


def _read_call(call_id: str = "c1"):
    return chunk(calls=[delta(call_id, "read_file", _READ)])


def _guard_warnings(caplog) -> list[str]:
    return [m for m in caplog.only("warning").messages if _GUARD_WARNING in m]


def _frame_names(record: dict) -> list[str]:
    names, tb = [], record["exception"].traceback
    while tb is not None:
        names.append(tb.tb_frame.f_code.co_name)
        tb = tb.tb_next
    return names


def _assert_failed(loop, stage: str, message: str) -> None:
    """The turn ended ``failed`` at ``stage``, reported once, and published once."""
    assert loop.outcome == TurnOutcome("failed", stage, message, True)
    assert loop.error == message
    assert loop.cb.system == [message]


class _ProbeContext(FakeContext):
    async def detect_context_length(self):
        raise RuntimeError("probe exploded")


class _BrokenSchemas(RecordingRegistry):
    def get_schemas(self, tags=None):
        raise RuntimeError("schemas exploded")


class _Unprintable(RuntimeError):
    """An exception a third-party SDK could raise whose text cannot be built."""

    def __str__(self):
        raise ValueError("no text")


# -- A collaborator that raises before the request (E11) -----------------------


@pytest.mark.parametrize(
    ("collaborator", "stage", "prefix"),
    [
        ("detect_context_length", "context", "the context manager failed"),
        ("pre_iteration_hook", "hook", "the pre-iteration hook failed"),
        ("get_schemas", "tools", "preparing the tool calls failed"),
        ("prepare_messages", "context", "the context manager failed"),
    ],
)
def test_a_collaborator_that_raises_before_the_request_fails_the_turn_at_its_stage(
    collaborator, stage, prefix
):
    """Baseline regression: each of these escapes ``run()`` today (E11).

    Driven by the real collaborator raising: the context manager, the iteration hook, the
    registry's ``get_schemas``. After: ``failed`` at the collaborator's stage, with its message.
    """
    registry = _BrokenSchemas() if collaborator == "get_schemas" else RecordingRegistry()
    context = FakeContext()
    config: dict[str, Any] = {}
    if collaborator == "detect_context_length":
        context = _ProbeContext()
    elif collaborator == "prepare_messages":
        context = FakeContext(raises={"prepare_messages": RuntimeError("probe exploded")})
    elif collaborator == "pre_iteration_hook":

        async def hook(messages):
            raise RuntimeError("probe exploded")

        config["pre_iteration_hook"] = hook
    detail = "schemas exploded" if collaborator == "get_schemas" else "probe exploded"
    provider = ScriptedProvider([chunk(content="never asked")])
    loop = make_loop(provider, registry=registry, context=context, **config)

    escaped = escape(run_turn, loop)

    assert escaped is None
    _assert_failed(loop, stage, f"Error: {prefix}: {detail}")
    assert provider.calls == 0


# -- A failure in the stream, by who raised ----------------------------------


def test_a_display_callback_that_raises_mid_stream_is_a_ui_failure(loguru_caplog):
    """Baseline regression: today the turn blames the LLM and logs "LLM stream failed" (E7).

    Driven by an ``on_assistant_content`` callback that raises while the reply streams. After:
    ``failed``/``ui`` with the user-interface message, and the one error record's traceback
    names the callback that raised.
    """
    callbacks = RecordingCallbacks(raises={"on_assistant_content": RuntimeError("widget exploded")})
    loop = make_loop(ScriptedProvider([chunk(content="hello")]), callbacks=callbacks)

    escaped = escape(run_turn, loop)

    assert escaped is None
    _assert_failed(loop, "ui", "Error: the user interface failed: widget exploded")
    records = loguru_caplog.only("error").records
    assert [r["message"] for r in records] == ["Chat turn raised (stage=ui)"]
    assert "on_assistant_content" in _frame_names(records[0])


@pytest.mark.allows_internal_turn_failure
@pytest.mark.parametrize(
    "script",
    [
        pytest.param([chunk(calls=[delta("c1", "read_file", 5)])], id="new-call"),
        pytest.param(
            [
                chunk(calls=[delta("c1", "read_file", '{"file_path": ', index=0)]),
                chunk(calls=[delta("", "", 5, index=0)]),
            ],
            id="continuation",
        ),
    ],
)
def test_a_delta_whose_arguments_are_not_text_is_an_internal_failure(script):
    """Baseline regression: assembly failing is blamed on the LLM today (E22).

    Driven by a delta whose ``arguments`` is not text, the shape a broken provider chunk has.
    The loop's own code raises while it assembles the call. After: ``failed``/``internal``.
    """
    loop = make_loop(ScriptedProvider(script))

    escaped = escape(run_turn, loop)

    assert escaped is None
    assert loop.outcome is not None
    assert (loop.outcome.status, loop.outcome.stage) == ("failed", "internal")
    assert loop.outcome.message is not None
    assert loop.outcome.message.startswith("Error: internal error in the chat loop: ")
    assert loop.outcome.reported is True
    assert loop.cb.system == [loop.outcome.message]


def test_an_exception_that_cannot_print_gets_the_fixed_text():
    """Baseline regression: building the message raises inside the stream handler today.

    Driven by a provider that raises an exception whose ``__str__`` raises. After: the turn is
    ``failed``/``llm`` with the fixed fallback text, and the guard logs one warning.
    """
    loop = make_loop(ScriptedProvider([_Unprintable()]))

    escaped = escape(run_turn, loop)

    assert escaped is None
    _assert_failed(loop, "llm", _FALLBACK_TEXT)


def test_the_closing_stop_cannot_replace_the_providers_failure(loguru_caplog):
    """Baseline regression: the closer's exception replaces the provider's and escapes today.

    Driven by a provider that raises and an ``on_thinking_stop`` callback that raises too. After:
    ``failed``/``llm`` with the provider's message, and one guard warning for the closer.
    """
    callbacks = RecordingCallbacks(raises={"on_thinking_stop": RuntimeError("stop exploded")})
    loop = make_loop(ScriptedProvider([RuntimeError("boom")]), callbacks=callbacks)

    escaped = escape(run_turn, loop)

    assert escaped is None
    _assert_failed(loop, "llm", "Error: boom")
    assert _guard_warnings(loguru_caplog) == ["closing thinking stop raised; continuing without it"]


def test_a_closing_stop_that_raises_after_a_clean_stream_is_a_ui_failure():
    """Baseline regression: the second ``on_thinking_stop`` escapes today.

    Driven by a stream of content, then late reasoning, then its end, with the second stop
    raising. That shape keeps its two stops after step 7. After: ``failed``/``ui``.
    """
    stops: list[int] = []

    def second_stop_raises():
        stops.append(len(stops) + 1)
        if len(stops) == 2:
            raise RuntimeError("stop exploded")

    callbacks = RecordingCallbacks(raises={"on_thinking_stop": second_stop_raises})
    provider = ScriptedProvider([chunk(content="hello"), chunk(reasoning="late")])
    loop = make_loop(provider, callbacks=callbacks)

    escaped = escape(run_turn, loop)

    assert escaped is None
    assert stops == [1, 2]
    _assert_failed(loop, "ui", "Error: the user interface failed: stop exploded")


def test_a_failing_iteration_event_leaves_a_completed_turn_completed(loguru_caplog):
    """Baseline regression: an ``emit_event`` that raises for the iteration event escapes today.

    Driven through loguru, the third-party seam: a sink with ``catch=False`` that raises on the
    ``iteration`` record. After: the text reply still ends ``completed``, with one guard warning.
    """

    def sink(message):
        if message.record["extra"].get("evt") == "iteration":
            raise RuntimeError("sink exploded")

    sink_id = logger.add(sink, level=0, catch=False, format="{message}")
    try:
        loop = make_loop(ScriptedProvider([chunk(content="hello")]))
        escaped = escape(run_turn, loop)
    finally:
        logger.remove(sink_id)

    assert escaped is None
    assert loop.outcome == TurnOutcome("completed")
    assert loop.error is None
    assert _guard_warnings(loguru_caplog) == ["iteration event raised; continuing without it"]


def test_a_provider_failure_after_a_tool_batch_is_still_an_llm_failure():
    """Preservation: the batch's stage marker does not outlive the batch.

    The first reply runs a tool; the provider raises on the next request. The turn is
    ``failed``/``llm``, as it is before the change.
    """
    provider = ScriptedProvider([_read_call()], [RuntimeError("boom")])
    loop = make_loop(provider)

    run_turn(loop)

    _assert_failed(loop, "llm", "Error: boom")
    assert provider.calls == 2


# -- A failure in the loop's own result processing (E18) ----------------------


@pytest.mark.allows_internal_turn_failure
def test_a_tool_result_the_loop_cannot_process_is_an_internal_failure_with_history_settled():
    """Baseline regression: a result the loop's own code raises on escapes ``run()`` today (E18).

    Driven by a real input: a ``read_file`` result of JSON nested 10,000 deep. The loop parses
    every result to look for an escalation, and ``json.loads`` raises ``RecursionError`` on it.
    After: ``failed``/``internal``, and the call still has its one tool message.
    """
    nested = "[" * 10_000 + "]" * 10_000
    registry = RecordingRegistry(results={"read_file": nested})
    loop = make_loop(ScriptedProvider([_read_call()]), registry=registry)

    escaped = escape(run_turn, loop)

    assert escaped is None
    assert loop.outcome is not None
    assert (loop.outcome.status, loop.outcome.stage) == ("failed", "internal")
    assert loop.outcome.message is not None
    assert loop.outcome.message.startswith("Error: internal error in the chat loop: ")
    assert loop.outcome.reported is True
    assert [m["tool_call_id"] for m in tool_messages(loop)] == ["c1"]


# -- A callback that raises at the loop's own checks (E21) ---------------------


def test_a_cancel_poll_that_raises_at_the_loops_check_is_a_ui_failure():
    """Baseline regression: ``is_cancelled`` raising at the loop's checks escapes today (E21).

    Driven by an ``is_cancelled`` callback that raises. After: ``failed``/``ui``.
    """
    callbacks = RecordingCallbacks(raises={"is_cancelled": RuntimeError("poll exploded")})
    provider = ScriptedProvider([chunk(content="never asked")])
    loop = make_loop(provider, callbacks=callbacks)

    escaped = escape(run_turn, loop)

    assert escaped is None
    _assert_failed(loop, "ui", "Error: the user interface failed: poll exploded")
    assert provider.calls == 0


# -- The report ---------------------------------------------------------------


def test_a_receiver_that_raises_keeps_the_outcome_and_is_called_once(loguru_caplog):
    """Baseline regression: a raising ``on_system_message`` escapes with ``.error`` set today (E20).

    Driven by a receiver that raises while the iteration cap (E3) is reported; it also records
    what the loop shows it. After: the outcome is kept with ``reported`` False, the receiver was
    called once and saw neither an outcome nor an error (the turn publishes once, at its end),
    and the guard logs one warning.
    """
    seen: list[tuple[Any, Any]] = []

    def receiver(text):
        seen.append((loop.outcome, loop.error))
        raise RuntimeError("receiver exploded")

    callbacks = RecordingCallbacks(raises={"on_system_message": receiver})
    loop = make_loop(ScriptedProvider([_read_call()]), callbacks=callbacks, max_iterations=1)

    escaped = escape(run_turn, loop)

    assert escaped is None
    assert len(callbacks.of("on_system_message")) == 1
    assert seen == [(None, None)]
    assert loop.outcome is not None
    assert (loop.outcome.status, loop.outcome.stage, loop.outcome.reported) == ("failed", "limit", False)
    assert loop.outcome.message is not None
    assert loop.outcome.message.startswith("Error: stopped after 1 LLM calls")
    assert loop.error == loop.outcome.message
    assert _guard_warnings(loguru_caplog) == ["failure report raised; continuing without it"]


def test_a_prompt_that_raises_fails_the_turn_at_the_confirmation_stage():
    """Baseline regression: a confirmation prompt that raises escapes ``run()`` today (E14, D3).

    Driven by a callback whose ``request_confirmation`` raises, with a confirmed write followed
    by a read. After: ``failed``/``confirmation``; each call keeps settlement's cancelled text
    and neither ran.
    """

    def prompt_raises(name, arguments):
        raise RuntimeError("dialog exploded")

    callbacks = RecordingCallbacks(confirm=prompt_raises)
    registry = RecordingRegistry()
    provider = ScriptedProvider(
        [chunk(calls=[delta("c1", "file_editor", _WRITE), delta("c2", "read_file", _READ)])]
    )
    loop = make_loop(provider, registry=registry, callbacks=callbacks, permissions={"r"})

    escaped = escape(run_turn, loop)

    assert escaped is None
    _assert_failed(loop, "confirmation", "Error: the confirmation prompt failed: dialog exploded")
    assert {m["tool_call_id"]: m["content"] for m in tool_messages(loop)} == {
        "c1": "Tool call was cancelled before it ran.",
        "c2": "Tool call was cancelled before it ran.",
    }
    assert registry.calls == []


# -- The records ----------------------------------------------------------------


def test_the_iteration_cap_logs_one_error_record_without_a_traceback(loguru_caplog):
    """Baseline regression: the iteration cap logs no error record today (E3)."""
    loop = make_loop(ScriptedProvider([_read_call()]), max_iterations=2)

    run_turn(loop)

    records = loguru_caplog.only("error").records
    assert [r["message"] for r in records] == ["Turn stopped after 2 LLM calls (max_iterations)"]
    assert records[0]["exception"] is None
    assert records[0]["extra"]["channel"] == "llm"


def test_the_reasoning_only_limit_logs_one_error_record_without_a_traceback(loguru_caplog):
    """Baseline regression: the reasoning-only limit logs no error record today (E5)."""
    loop = make_loop(ScriptedProvider([chunk(reasoning="hmm")]))

    run_turn(loop)

    records = loguru_caplog.only("error").records
    assert [r["message"] for r in records] == [
        "Turn stopped: the model returned only reasoning 3 times in a row"
    ]
    assert records[0]["exception"] is None
    assert records[0]["extra"]["channel"] == "llm"
