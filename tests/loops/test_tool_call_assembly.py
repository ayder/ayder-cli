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

Step 14 (R9b, D6) adds fragments that carry no key (no index, id or name): they continue the most
recent call only when every earlier call is sealed (its arguments are non-empty text that decodes to
a JSON object), and are refused otherwise. A refused fragment goes to one shared nameless call, which
is refused as before, and the calls that were not sealed at that point do not run.

Step 15 (R9c, R9d) gives each call one UI key, unique in the chat session, that every start and
completion of its item uses: the provider's id when it is non-empty, not a placeholder (``idx_``,
``dummy_``) and not used before in the session, otherwise ``<id or "call">#<n>``. A split call's
first child keeps the item opened for its parent. History keeps the provider's id.

Kind: baseline regression unless a docstring says preservation. Environment: local-faked (no
network; the provider and registry are the fakes in ``turn_fakes``). Layer: unit.

Every case is a real input: scripted provider deltas (the shapes real providers stream).
"""

from __future__ import annotations

import pytest

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


# -- Step 14: fragments with no key (R9b, D6; B3) ---------------------------------------------------------------------

_D6 = (
    "Error: part of this call's arguments could not be attributed to it, so it was not run. "
    "Send the call again."
)


def _ran(loop) -> list[tuple[str, dict]]:
    return list(loop.registry.calls)


def test_fragments_with_no_key_continue_the_only_call():
    """Baseline regression, P3 B3: the fragments open a nameless call and the real call keeps only
    its first delta's arguments, so it is refused for its missing argument (zero executions).

    Driven by one call and then its argument fragments, which carry no index, id or name. After:
    the call runs with the joined arguments.
    """
    loop = _turn(delta("c1", "read_file", '{"file_path": '), delta("", "", '"a.py"}'))

    assert _ran(loop) == [("read_file", {"file_path": "a.py"})]


def test_fragments_with_no_key_that_continue_a_call_open_no_refused_call():
    """Baseline regression, P3 B3: the fragments also become a nameless call that is refused."""
    loop = _turn(delta("c1", "read_file", '{"file_path": '), delta("", "", '"a.py"}'))

    assert [c["id"] for c in assistant_calls(loop)] == ["c1"]


def test_fragments_with_no_key_continue_the_latest_call_after_a_sealed_one():
    """Baseline regression, L4 without the index: the first call is complete, the second streams.

    The first call is sealed when the second opens, so the fragments that follow are the second
    call's. After: both calls run with their full arguments.
    """
    loop = _turn(
        delta("c1", "read_file", _A),
        delta("c2", "file_explorer", '{"path": '),
        delta("", "", '"."}'),
    )

    assert _calls_by_id(loop) == {
        "c1": ("read_file", _A),
        "c2": ("file_explorer", '{"path": "."}'),
    }


def test_each_call_of_the_sequence_runs_with_its_full_arguments():
    """Baseline regression, L4 without the index: the calls run with partial arguments today."""
    loop = _turn(
        delta("c1", "read_file", _A),
        delta("c2", "file_explorer", '{"path": '),
        delta("", "", '"."}'),
    )

    assert sorted(_ran(loop)) == [("file_explorer", {"path": "."}), ("read_file", {"file_path": "a.py"})]


# Two calls whose arguments are all optional, so a refusal for a missing argument cannot hide a
# call that runs with nothing. Fragments that cannot be attributed to either:
_AMBIGUOUS = pytest.param
_AMBIGUOUS_SHAPES = [
    pytest.param(
        [delta("a1", "opt_a", ""), delta("b1", "opt_b", ""), delta("", "", '{"x": 1}')],
        (1, 8),
        id="two-calls-started-then-one-fragment",
    ),
    pytest.param(
        [
            delta("a1", "opt_a", '{"x": '),
            delta("b1", "opt_b", '{"y": '),
            delta("", "", "1}"),
            delta("", "", "2}"),
        ],
        (2, 4),
        id="two-calls-interleaved",
    ),
]


def _ambiguous_turn(probe_tool, deltas):
    probe_tool("opt_a")
    probe_tool("opt_b")
    return _turn(*deltas)


@pytest.mark.parametrize(("deltas", "refused"), _AMBIGUOUS_SHAPES)
def test_fragments_that_belong_to_no_known_call_stop_every_unsealed_call_from_running(
    probe_tool, deltas, refused
):
    """Baseline regression, D6: both calls run with what they have today.

    After: nothing runs.
    """
    loop = _ambiguous_turn(probe_tool, deltas)

    assert _ran(loop) == []


@pytest.mark.parametrize(("deltas", "refused"), _AMBIGUOUS_SHAPES)
def test_each_unsealed_call_gets_the_unattributed_result(probe_tool, deltas, refused):
    """Baseline regression, D6: the calls' own results are what they ran to, today."""
    loop = _ambiguous_turn(probe_tool, deltas)

    results = _results_by_id(loop)
    assert (results["a1"], results["b1"]) == (_D6, _D6)


@pytest.mark.parametrize(("deltas", "refused"), _AMBIGUOUS_SHAPES)
def test_refused_fragments_are_logged_once_with_their_count_and_size(
    probe_tool, loguru_caplog, deltas, refused
):
    """Baseline regression, R9b: nothing is logged today. After: one record for the response,
    carrying the number of fragments and their total size, never their text."""
    _ambiguous_turn(probe_tool, deltas)

    count, chars = refused
    messages = [m for m in loguru_caplog.only("warning").messages if m.startswith("Refused ")]
    assert messages == [f"Refused {count} unattributable tool-call fragment(s) ({chars} chars)"]


@pytest.mark.parametrize(("deltas", "refused"), _AMBIGUOUS_SHAPES)
def test_refused_fragments_share_one_nameless_call_that_is_refused_as_before(
    probe_tool, deltas, refused
):
    """Preservation: the fragments collect in one nameless call, which is refused for its name.

    Passes before and after; only the calls beside it change.
    """
    loop = _ambiguous_turn(probe_tool, deltas)

    refused_calls = [
        m for m in tool_messages(loop) if m["content"].startswith("Error: tool name is empty or unknown")
    ]
    assert len(refused_calls) == 1


def test_a_truncated_last_call_keeps_the_repaired_arguments_rule():
    """Preservation: no fragment is refused, so a call cut off by the output limit still runs with
    its arguments repaired, and its result says so. Passes before and after."""
    loop = _turn(delta("c1", "read_file", '{"file_path": "a.py"'))

    assert _ran(loop) == [("read_file", {"file_path": "a.py"})]
    (message,) = tool_messages(loop)
    assert message["content"].startswith("[harness] arguments were truncated and repaired")


# -- Step 15: UI keys (R9c, R9d; B5) -------------------------------------------------------------------------------------


def _turns(*responses):
    """One turn whose replies are ``responses`` (each a list of deltas), then a text reply."""
    scripts = [[chunk(calls=list(deltas))] for deltas in responses] + [[chunk(content="done")]]
    loop = make_loop(ScriptedProvider(*scripts), registry=_EchoRegistry())
    run_turn(loop)
    return loop


def _opened(loop) -> list[str]:
    """The item keys, in the order their items opened."""
    return list(loop.cb.starts_by_key())


def _finished(loop) -> list[str]:
    return list(loop.cb.completes_by_key())


def test_a_placeholder_id_that_a_real_id_replaces_opens_one_item():
    """Baseline regression, P3 B5b: ``on_tool_start`` fires for ``idx_0`` and again for ``call_x``.

    Driven by the OpenAI shape: the name arrives with the placeholder id, the real id on the next
    delta of the same index. After: one key.
    """
    loop = _turns(
        [delta("idx_0", "read_file", "", index=0), delta("call_x", "", _A, index=0)],
    )

    assert len(_opened(loop)) == 1


def test_the_item_of_a_placeholder_id_that_a_real_id_replaces_is_finished():
    """Baseline regression, P3 B5b: only ``call_x`` completes today, so ``idx_0``'s item never ends."""
    loop = _turns(
        [delta("idx_0", "read_file", "", index=0), delta("call_x", "", _A, index=0)],
    )

    assert _finished(loop) == _opened(loop)


def test_history_keeps_the_real_id_that_replaced_the_placeholder():
    """Preservation: the assistant entry and its result carry ``call_x``, not the UI key."""
    loop = _turns(
        [delta("idx_0", "read_file", "", index=0), delta("call_x", "", _A, index=0)],
    )

    assert list(_calls_by_id(loop)) == ["call_x"]
    assert list(_results_by_id(loop)) == ["call_x"]


def test_the_first_child_of_a_split_call_finishes_the_item_opened_for_its_parent():
    """Baseline regression, P7: ``p`` is started while streaming and never completed today.

    Driven by one call whose arguments hold two concatenated objects, which the loop splits into
    ``p_split_0`` and ``p_split_1``.
    """
    loop = _turns([delta("p", "read_file", _A + _B)])

    assert "p" in _finished(loop)


def test_the_first_child_of_a_split_call_opens_no_item_of_its_own():
    """Baseline regression, R9d: the parent's item is the first child's, so ``p_split_0`` has none."""
    loop = _turns([delta("p", "read_file", _A + _B)])

    assert "p_split_0" not in _opened(loop)


def test_the_other_child_of_a_split_call_opens_and_finishes_its_own_item():
    """Preservation: ``p_split_1`` is started once and completed once, today and after."""
    loop = _turns([delta("p", "read_file", _A + _B)])

    assert loop.cb.starts_by_key()["p_split_1"][-1] == ("read_file", {"file_path": "b.py"})
    assert len(loop.cb.completes_by_key()["p_split_1"]) == 1


def test_a_call_with_an_empty_id_gets_a_generated_key():
    """Baseline regression, R9c: the item is opened under the empty id today.

    After: ``call#<n>``, one key for the start and the completion, while history keeps ``call_0``.
    """
    loop = _turns([delta("", "read_file", _A)])

    assert _opened(loop) == ["call#1"]
    assert _finished(loop) == ["call#1"]


def test_a_provider_id_with_a_placeholder_prefix_gets_a_generated_key():
    """Baseline regression, R9c: ``dummy_0`` is the item's key today. After: ``dummy_0#1``."""
    loop = _turns([delta("dummy_0", "read_file", _A)])

    assert _opened(loop) == ["dummy_0#1"]


def test_a_provider_id_used_earlier_in_the_session_gets_a_generated_key_that_skips_used_ones():
    """Baseline regression, R9c: the second ``r`` reuses the first ``r``'s key today.

    Iteration 1 sends the literal ``r#1`` and ``r``; iteration 2 sends ``r`` again. The generated
    ``r#1`` would collide with the literal one, so the counter skips it: ``r#2``.
    """
    loop = _turns(
        [delta("r#1", "read_file", _A), delta("r", "read_file", _B)],
        [delta("r", "read_file", _A)],
    )

    assert _opened(loop) == ["r#1", "r", "r#2"]
    assert _finished(loop) == ["r#1", "r", "r#2"]


def test_history_keeps_the_provider_id_when_the_ui_key_is_generated():
    """Preservation: the repeated ``r`` stays ``r`` in history; only the UI key differs."""
    loop = _turns([delta("r", "read_file", _A)], [delta("r", "read_file", _B)])

    assert [c["id"] for c in assistant_calls(loop)] == ["r", "r"]


def test_a_provider_id_that_is_unique_in_the_session_is_its_own_key():
    """Preservation: ``tests/ui/test_tui_chat_loop.py`` expects ``c1`` for a call ``c1``."""
    loop = _turns([delta("c1", "read_file", _A)], [delta("c2", "read_file", _B)])

    assert _opened(loop) == ["c1", "c2"]
    assert _finished(loop) == ["c1", "c2"]


def test_the_batch_called_directly_falls_back_to_the_call_id():
    """Preservation: a caller that passes no key map gets the call's own id for its item."""
    import asyncio

    from ayder_cli.providers.base import _FunctionCall, _ToolCall

    loop = make_loop(ScriptedProvider([chunk(content="unused")]), registry=_EchoRegistry())
    call = _ToolCall(id="c9", function=_FunctionCall(name="read_file", arguments=_A))

    asyncio.run(loop._execute_tool_calls([call]))

    assert _opened(loop) == ["c9"]
    assert _finished(loop) == ["c9"]
