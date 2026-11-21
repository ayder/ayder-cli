"""Every tool completion the loop reports carries the status it knows (plan step 12, R4a).

The loop used to hand ``on_tool_complete`` a plain string, so a receiver had to guess a call's
outcome from the text: a refusal, a denial and a skipped call all looked like successes, and a
successful result that began with ``Error`` looked like a failure. Now the argument is a
``str`` subclass with a ``status`` (``ok``, ``error``, ``denied``, ``skipped`` or ``not_run``);
history keeps the plain text. A result with no known status (a plain ``str`` from the agent tool or
a plugin) carries none, so the receiver's own text rule still applies.

Kind: baseline regression unless a docstring says preservation. Environment: local-faked (no
network; the provider, callbacks and registry are the fakes in ``turn_fakes``). Layer: unit.

The tests read ``getattr(result, "status", None)`` from the argument and never import the carrier
type, so every case fails at its assertion on the parent.
"""

from __future__ import annotations

import pytest

from ayder_cli.core.result import ToolError, ToolSuccess
from tests.loops.turn_fakes import (
    RecordingCallbacks,
    RecordingRegistry,
    ScriptedProvider,
    chunk,
    delta,
    make_loop,
    run_turn,
    tool_messages,
)

_READ = '{"file_path": "a.py"}'
_WRITE = '{"file_path": "a.py", "operation": "write", "content": "x"}'


def _status(loop, call_id: str = "c1"):
    """The status of the first completion the loop reported for ``call_id``."""
    return getattr(loop.cb.completes_by_key()[call_id][0], "status", None)


def _turn(calls, *, registry=None, callbacks=None, permissions=None):
    """One reply with ``calls``, then a text reply; run to the end."""
    provider = ScriptedProvider([chunk(calls=calls)], [chunk(content="done")])
    extra = {} if permissions is None else {"permissions": permissions}
    loop = make_loop(provider, registry=registry, callbacks=callbacks, **extra)
    run_turn(loop)
    return loop


# -- Calls the loop refuses ------------------------------------------------------------


@pytest.mark.parametrize(
    "call",
    [
        pytest.param(delta("c1", "", "{}"), id="no-tool-name"),
        pytest.param(delta("c1", "read_file", "{}"), id="missing-required-argument"),
        pytest.param(delta("c1", "read_file", "null"), id="arguments-not-an-object"),
    ],
)
def test_a_refused_call_completes_with_the_error_status(call):
    """Baseline regression: the refusal's text is all the receiver gets today."""
    loop = _turn([call])

    assert _status(loop) == "error"


# -- Calls that ran --------------------------------------------------------------------------


def test_a_tool_error_result_completes_with_the_error_status():
    """Baseline regression: a ``ToolError`` that does not start with "Error" reads as success today."""
    registry = RecordingRegistry(results={"read_file": ToolError("command is required")})

    loop = _turn([delta("c1", "read_file", _READ)], registry=registry)

    assert _status(loop) == "error"


def test_a_tool_success_result_completes_with_the_ok_status():
    """Baseline regression: nothing says a ``ToolSuccess`` succeeded (it can begin with "Error")."""
    registry = RecordingRegistry(results={"read_file": ToolSuccess("Error: this is the file's text")})

    loop = _turn([delta("c1", "read_file", _READ)], registry=registry)

    assert _status(loop) == "ok"


def test_a_tool_that_raises_completes_with_the_error_status():
    """Baseline regression: the exception's text is all the receiver gets today."""
    registry = RecordingRegistry(raises={"read_file": RuntimeError("tool exploded")})

    loop = _turn([delta("c1", "read_file", _READ)], registry=registry)

    assert _status(loop) == "error"


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        pytest.param(ToolError("command is required"), "error", id="tool-error"),
        pytest.param(ToolSuccess("written"), "ok", id="tool-success"),
    ],
)
def test_a_confirmed_call_completes_with_the_status_of_its_result(result, expected):
    """Baseline regression: the confirmed path reports plain text too."""
    registry = RecordingRegistry(results={"file_editor": result})

    loop = _turn(
        [delta("c1", "file_editor", _WRITE)],
        registry=registry,
        callbacks=RecordingCallbacks(confirm="approve"),
        permissions={"r"},
    )

    assert _status(loop) == expected


def test_a_confirmed_call_that_raises_completes_with_the_error_status():
    """Baseline regression: the confirmed path converts the failure to its result (step 2)."""
    registry = RecordingRegistry(raises={"file_editor": RuntimeError("tool exploded")})

    loop = _turn(
        [delta("c1", "file_editor", _WRITE)],
        registry=registry,
        callbacks=RecordingCallbacks(confirm="approve"),
        permissions={"r"},
    )

    assert _status(loop) == "error"


# -- The user's answer to a confirmation ---------------------------------------------------


def test_a_denied_call_completes_with_the_denied_status():
    """Baseline regression: "Tool call denied by user." reads as a success today."""
    loop = _turn(
        [delta("c1", "file_editor", _WRITE)],
        callbacks=RecordingCallbacks(confirm="deny"),
        permissions={"r"},
    )

    assert _status(loop) == "denied"


def test_an_instruct_answer_completes_its_call_with_the_denied_status():
    """Baseline regression: the instruct answer's text reads as a success today."""
    loop = _turn(
        [delta("c1", "file_editor", _WRITE), delta("c2", "read_file", _READ)],
        callbacks=RecordingCallbacks(confirm="instruct"),
        permissions={"r"},
    )

    assert _status(loop, "c1") == "denied"


def test_the_call_after_an_instruct_answer_completes_with_the_skipped_status():
    """Baseline regression: "Tool call skipped." reads as a success today."""
    loop = _turn(
        [delta("c1", "file_editor", _WRITE), delta("c2", "read_file", _READ)],
        callbacks=RecordingCallbacks(confirm="instruct"),
        permissions={"r"},
    )

    assert _status(loop, "c2") == "skipped"


# -- The before-run notice ---------------------------------------------------------------------


def test_a_call_that_saw_the_cancel_flag_before_it_started_completes_with_the_not_run_status():
    """Baseline regression: the worker returns the before-run notice and the waiter collects it.

    A callback sets the cooperative cancel flag while the batch announces the call (the second
    ``on_tool_start``, which carries the parsed arguments), so the worker sees it before it starts.
    """
    callbacks = RecordingCallbacks()
    callbacks.raises["on_tool_start"] = lambda call_id, name, arguments: (
        setattr(callbacks, "cancelled", True) if arguments else None
    )
    registry = RecordingRegistry()

    loop = _turn([delta("c1", "read_file", _READ)], registry=registry, callbacks=callbacks)

    assert registry.calls == []  # premise: the tool never started
    assert _status(loop) == "not_run"


# -- What does not change (preservation) -------------------------------------------------------


def test_a_plain_string_result_completes_with_no_status():
    """Preservation: a tool that returns a plain ``str`` (the agent tool, some plugins) has no
    known status, so the receiver's text rule still applies. Passes before and after."""
    registry = RecordingRegistry(results={"read_file": "plain text result"})

    loop = _turn([delta("c1", "read_file", _READ)], registry=registry)

    assert _status(loop) is None


def test_history_keeps_the_plain_text_of_every_kind_of_result():
    """Preservation: the tool messages are plain ``str`` with the same text, whatever the status."""
    registry = RecordingRegistry(
        results={"read_file": ToolSuccess("the file"), "file_explorer": ToolError("no match")}
    )

    loop = _turn(
        [
            delta("c1", "read_file", _READ),
            delta("c2", "file_explorer", '{"path": "."}'),
            delta("c3", "", "{}"),
        ],
        registry=registry,
    )

    contents = {m["tool_call_id"]: m["content"] for m in tool_messages(loop)}
    assert contents["c1"] == "the file"
    assert contents["c2"] == "no match"
    assert contents["c3"].startswith("Error: tool name is empty or unknown")
    assert all(type(content) is str for content in contents.values())
