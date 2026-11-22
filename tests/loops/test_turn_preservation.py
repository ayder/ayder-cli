"""Behaviour the turn-integrity work must keep (plan step 0).

Every test here passes on main and must keep passing after each step of
plans/2026-11-21-chat-loop-turn-integrity.md. They pin how streamed tool-call
fragments merge, what the UI is told while a call is assembled, and two
refusals that produce a result without running the tool.

Kind: preservation. Environment: local-faked (no network; the provider,
callbacks and registry are the fakes in ``turn_fakes``). Layer: unit.
"""

from __future__ import annotations

from tests.loops.turn_fakes import (
    RecordingCallbacks,
    ScriptedProvider,
    assistant_calls,
    chunk,
    delta,
    make_loop,
    run_turn,
    tool_messages,
)

_WRITE_ARGS = '{"file_path": "a.py", "operation": "write", "content": "x"}'


def test_fragments_at_one_index_merge_into_one_call():
    """Preservation, local-faked, unit: deltas sharing a stream index are one call.

    The first delta carries the id, the name and half the arguments; the
    second has an empty id and name and the rest. One call runs with the joined
    arguments and history holds one call. The key is told twice: the streamed
    start when the name arrives, then the start with the parsed arguments
    before execution.
    """
    provider = ScriptedProvider(
        [
            chunk(calls=[delta("call_1", "read_file", '{"file_path": "a', index=0)]),
            chunk(calls=[delta("", "", '.py"}', index=0)]),
        ],
        [chunk(content="done")],
    )
    loop = make_loop(provider)

    run_turn(loop)

    assert loop.registry.calls == [("read_file", {"file_path": "a.py"})]
    (call,) = assistant_calls(loop)
    assert call["id"] == "call_1"
    assert call["function"] == {"name": "read_file", "arguments": '{"file_path": "a.py"}'}
    (tool_message,) = tool_messages(loop)
    assert tool_message["tool_call_id"] == "call_1"
    assert tool_message["content"] == "ok"
    assert loop.cb.starts_by_key() == {
        "call_1": [("read_file", {}), ("read_file", {"file_path": "a.py"})]
    }
    assert loop.cb.completes_by_key() == {"call_1": ["ok"]}
    assert loop.error is None


def test_a_name_that_arrives_late_joins_its_call():
    """Preservation, local-faked, unit: an id first, the name later, is one call.

    The first delta has an id and part of the arguments but no name, so the
    UI hears nothing yet. The name arrives at the same index: history holds
    one call, it runs with the full arguments and it completes once. Its key
    gets two ``on_tool_start`` calls: the name with ``{}`` when the name
    arrives, then the parsed arguments before execution.
    """
    provider = ScriptedProvider(
        [
            chunk(calls=[delta("call_1", "", '{"file_path": ', index=0)]),
            chunk(calls=[delta("", "read_file", '"a.py"}', index=0)]),
        ],
        [chunk(content="done")],
    )
    loop = make_loop(provider)

    run_turn(loop)

    assert loop.registry.calls == [("read_file", {"file_path": "a.py"})]
    (call,) = assistant_calls(loop)
    assert call["id"] == "call_1"
    assert call["function"] == {"name": "read_file", "arguments": '{"file_path": "a.py"}'}
    assert [m["tool_call_id"] for m in tool_messages(loop)] == ["call_1"]
    assert loop.cb.starts_by_key() == {
        "call_1": [("read_file", {}), ("read_file", {"file_path": "a.py"})]
    }
    assert loop.cb.completes_by_key() == {"call_1": ["ok"]}
    assert loop.error is None


def test_a_call_with_no_name_is_refused_and_nothing_runs():
    """Preservation, local-faked, unit: an empty tool name gets an error result.

    The result reaches the UI and history as ``Error: tool name is empty or
    unknown...`` under the name ``unknown``; the registry is never asked to
    run anything and the turn goes on to the model's next reply.
    """
    provider = ScriptedProvider(
        [chunk(calls=[delta("call_1", "", "{}")])],
        [chunk(content="done")],
    )
    loop = make_loop(provider)

    run_turn(loop)

    assert loop.registry.calls == []
    (tool_message,) = tool_messages(loop)
    assert tool_message["tool_call_id"] == "call_1"
    assert tool_message["name"] == "unknown"
    assert tool_message["content"].startswith("Error: tool name is empty or unknown")
    assert loop.cb.starts_by_key() == {"call_1": [("unknown", {})]}
    assert loop.cb.completes_by_key() == {"call_1": [tool_message["content"]]}
    assert provider.calls == 2
    assert loop.error is None


def test_a_denied_confirmation_gives_a_result_and_nothing_runs():
    """Preservation, local-faked, unit: the user denies a write.

    ``Tool call denied by user.`` is the call's result in the UI and in
    history, so the model sees a tool result for its call; the registry is
    never asked to run it.
    """
    provider = ScriptedProvider(
        [chunk(calls=[delta("call_1", "file_editor", _WRITE_ARGS)])],
        [chunk(content="done")],
    )
    callbacks = RecordingCallbacks(confirm="deny")
    loop = make_loop(provider, callbacks=callbacks, permissions={"r"})

    run_turn(loop)

    assert loop.registry.calls == []
    assert [args[0] for _, args in callbacks.of("request_confirmation")] == ["file_editor"]
    (tool_message,) = tool_messages(loop)
    assert tool_message["tool_call_id"] == "call_1"
    assert tool_message["content"] == "Tool call denied by user."
    assert callbacks.completes_by_key() == {"call_1": ["Tool call denied by user."]}
    assert provider.calls == 2
    assert loop.error is None
