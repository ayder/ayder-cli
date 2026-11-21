"""A response's tool calls get distinct, non-empty ids, and no empty slots (plan step 13, R9a, R9e).

The loop assembled a response's streamed tool-call deltas into calls, keeping the provider's id
as the call's identity. Two calls that shared an id both ran and both history entries carried the
second call's result (P7); a call with an empty id was recorded with ``""``; a different tool that
reused an id (without an index) was merged into the earlier call; a padded slot that no delta
filled was recorded as a nameless call and refused; and a padded slot that a delta filled kept its
``dummy_N`` placeholder instead of the delta's id (P3 B5a). Now identity is settled before the
reply is appended: first occurrences keep their ids, a missing id becomes ``call_<position>``, a
repeated id ``X`` becomes ``X_<k>`` for its k-th occurrence, a filled slot takes its delta's id,
and an unfilled slot is absent.

Kind: baseline regression unless a docstring says preservation. Environment: local-faked (no
network; the provider and registry are the fakes in ``turn_fakes``). Layer: unit.

Every case is a real input: scripted provider deltas (the shapes real providers stream).
"""

from __future__ import annotations

from ayder_cli.core.result import ToolSuccess
from tests.loops.turn_fakes import (
    RecordingRegistry,
    ScriptedProvider,
    assistant_calls,
    chunk,
    delta,
    make_loop,
    run_turn,
    tool_messages,
)

_A = '{"file_path": "a.py"}'
_B = '{"file_path": "b.py"}'


class _EchoRegistry(RecordingRegistry):
    """Each tool answers with its own name and arguments, so a result says whose it is."""

    def execute(self, name, arguments):
        self.calls.append((name, dict(arguments)))
        return ToolSuccess(f"{name}:{sorted(arguments.items())}")


def _turn(*deltas):
    """One reply carrying ``deltas`` in one chunk, then a text reply; run to the end."""
    provider = ScriptedProvider([chunk(calls=list(deltas))], [chunk(content="done")])
    loop = make_loop(provider, registry=_EchoRegistry())
    run_turn(loop)
    return loop


def _calls_by_id(loop) -> dict[str, tuple[str, str]]:
    """The assistant's tool calls as ``{id: (name, arguments)}``."""
    return {c["id"]: (c["function"]["name"], c["function"]["arguments"]) for c in assistant_calls(loop)}


def _results_by_id(loop) -> dict[str, str]:
    return {m["tool_call_id"]: m["content"] for m in tool_messages(loop)}


# -- P7: two calls share an id --------------------------------------------------------------------


def test_two_calls_that_share_an_id_get_distinct_ids():
    """Baseline regression, P7: both calls keep ``call_1`` today.

    Driven by two calls with the id ``call_1`` at indices 0 and 1. After: the first keeps it, the
    second becomes ``call_1_2``.
    """
    loop = _turn(
        delta("call_1", "read_file", _A, index=0), delta("call_1", "read_file", _B, index=1)
    )

    assert [c["id"] for c in assistant_calls(loop)] == ["call_1", "call_1_2"]


def test_two_calls_that_share_an_id_each_keep_their_own_result():
    """Baseline regression, P7: both history entries carry the second call's result today."""
    loop = _turn(
        delta("call_1", "read_file", _A, index=0), delta("call_1", "read_file", _B, index=1)
    )

    assert _results_by_id(loop) == {
        "call_1": "read_file:[('file_path', 'a.py')]",
        "call_1_2": "read_file:[('file_path', 'b.py')]",
    }


# -- A different tool reuses an id, without an index ---------------------------------------------------


def test_a_different_tool_that_reuses_an_id_without_an_index_is_its_own_call():
    """Baseline regression: the live glm-5.3 shape. Today the two merge into one call.

    Each call keeps its own name and arguments (the first keeps the id; the second gets
    ``call_x_2``).
    """
    loop = _turn(
        delta("call_x", "read_file", _A), delta("call_x", "file_explorer", '{"path": "."}')
    )

    assert _calls_by_id(loop) == {
        "call_x": ("read_file", _A),
        "call_x_2": ("file_explorer", '{"path": "."}'),
    }


def test_a_different_tool_that_reuses_an_id_gets_the_result_of_its_own_call():
    """Baseline regression: the results are paired with their calls by id, since the concatenated
    JSON the merge produces is split and parallel completion order varies."""
    loop = _turn(
        delta("call_x", "read_file", _A), delta("call_x", "file_explorer", '{"path": "."}')
    )

    assert _results_by_id(loop) == {
        "call_x": "read_file:[('file_path', 'a.py')]",
        "call_x_2": "file_explorer:[('path', '.')]",
    }


# -- A missing id ---------------------------------------------------------------------------------------


def test_a_call_with_an_empty_id_gets_one_from_its_position():
    """Baseline regression: history carries ``""`` as the call's id today. After: ``call_0``."""
    loop = _turn(delta("", "read_file", _A))

    assert [c["id"] for c in assistant_calls(loop)] == ["call_0"]


def test_the_result_of_a_call_with_an_empty_id_carries_the_generated_id():
    """Baseline regression: its tool message says ``""`` today."""
    loop = _turn(delta("", "read_file", _A))

    assert [m["tool_call_id"] for m in tool_messages(loop)] == ["call_0"]


# -- Sparse slots --------------------------------------------------------------------------------------------


def test_deltas_at_index_one_only_leave_no_empty_slot_behind_them():
    """Baseline regression, R9e: a nameless ``dummy_0`` call is recorded, and refused, today."""
    loop = _turn(delta("c1", "read_file", _A, index=1))

    assert [c["id"] for c in assistant_calls(loop)] == ["c1"]


def test_a_delta_that_fills_a_padded_slot_gives_it_its_own_id():
    """Baseline regression, P3 B5a: the slot keeps its ``dummy_0`` placeholder today.

    Index 1 arrives first, then index 0 with the id ``call_a``.
    """
    loop = _turn(
        delta("call_b", "read_file", _B, index=1), delta("call_a", "read_file", _A, index=0)
    )

    assert [c["id"] for c in assistant_calls(loop)] == ["call_a", "call_b"]


# -- What does not change (preservation) -------------------------------------------------------------------


def test_a_filled_padded_slot_keeps_the_name_and_arguments_of_its_delta():
    """Preservation: the slot is filled in place, so its name and arguments are the delta's.

    Passes before and after; only the slot's id changed.
    """
    loop = _turn(
        delta("call_b", "read_file", _B, index=1), delta("call_a", "read_file", _A, index=0)
    )

    assert [c["function"]["arguments"] for c in assistant_calls(loop)] == [_A, _B]


def test_a_placeholder_id_is_replaced_by_the_real_id_that_arrives_later():
    """Preservation: an ``idx_`` placeholder takes the real id of a later delta at its index."""
    loop = _turn(
        delta("idx_0", "read_file", '{"file_path": ', index=0),
        delta("call_real", "", '"a.py"}', index=0),
    )

    assert _calls_by_id(loop) == {"call_real": ("read_file", _A)}


def test_unique_ids_and_a_second_call_that_merely_continues_are_unchanged():
    """Preservation: distinct ids stay as they are, and a delta that repeats an id with the same
    name continues its call (arguments join) rather than opening a new one."""
    loop = _turn(
        delta("c1", "read_file", '{"file_path": ', index=0),
        delta("c1", "read_file", '"a.py"}', index=0),
        delta("c2", "read_file", _B, index=1),
    )

    assert _calls_by_id(loop) == {"c1": ("read_file", _A), "c2": ("read_file", _B)}
