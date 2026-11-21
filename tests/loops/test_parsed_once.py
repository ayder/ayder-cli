"""A call's arguments are parsed once, and each consumer gets its own copy (plan step 20, R10; W1).

The loop parsed a call's argument text again for every consumer: history sanitization, validation,
the running display, the repeat signature, the confirmation preview and the executor. A truncated
call's repair logged its warnings each time (11 for one ``read_file`` call, P3), and a long argument
text was decoded and repaired over and over. Now ``run()`` parses each call once, right after
assembly, and validation, the displays, confirmation, execution and the repeat signature share the
result. It stays private: the parallel-safe predicate, the receivers of the running display and of
the confirmation preview, and the executor each get a deep copy, so a consumer that mutates its
arguments, however deeply nested, can change neither the other consumers nor the call that runs.
Execution keeps the raw text and its status, never the repaired JSON that history stores.

Kind: baseline regression unless a docstring says preservation. Environment: local-faked (no
network; the provider and registry are the fakes in ``turn_fakes``). Layer: unit.
"""

from __future__ import annotations

import asyncio

from ayder_cli.loops.chat_loop import _ParsedCall
from ayder_cli.providers.base import _FunctionCall, _ToolCall
from tests.loops.turn_fakes import (
    RecordingCallbacks,
    ScriptedProvider,
    chunk,
    delta,
    make_loop,
    run_turn,
    tool_messages,
)

_PARSE_WARNING_PREFIXES = (
    "Tool arguments JSON parse failed",
    "Recovered tool arguments",
    "Could not recover tool arguments",
    "Malformed tool arguments",
)
_WRITE = '{"file_path": "a.py", "operation": "write", "content": "x"}'


def _turn_with(*deltas, **make):
    """One reply carrying ``deltas``, then a text reply; run to the end."""
    provider = ScriptedProvider([chunk(calls=list(deltas))], [chunk(content="done")])
    loop = make_loop(provider, **make)
    run_turn(loop)
    return loop


# -- W1: one truncated call parses once ----------------------------------------------------------------


def test_a_truncated_call_logs_its_parse_warnings_once(loguru_caplog):
    """Baseline regression, W1 (P3): one truncated ``read_file`` call logs 11 parse warnings today.

    Driven by a call whose argument text is cut off inside a string, through a normal batch. After:
    three, one parse's two warnings (the failed decode and the repair) and the history notice.
    """
    _turn_with(delta("c1", "read_file", '{"file_path": "a.py'))

    warnings = [
        message
        for message in loguru_caplog.only("warning").messages
        if message.startswith(_PARSE_WARNING_PREFIXES)
    ]
    assert len(warnings) == 3, f"{len(warnings)} parse warnings"


def test_a_truncated_read_only_call_still_runs_with_its_repaired_arguments():
    """Preservation: the repair that every consumer shares is the one execution uses."""
    loop = _turn_with(delta("c1", "read_file", '{"file_path": "a.py'))

    assert loop.registry.calls == [("read_file", {"file_path": "a.py"})]


# -- Each consumer gets its own copy ----------------------------------------------------------------------


def test_a_predicate_that_mutates_its_arguments_and_then_raises_cannot_change_the_executed_call(
    probe_tool,
):
    """Preservation: the predicate's failure makes the call run alone (step 2), with the input the
    call was validated with. Holds today because execution parses again; after, because the
    predicate gets its own copy."""

    def predicate(args):
        args["items"].append("TAMPERED")
        args["extra"] = "TAMPERED"
        raise RuntimeError("predicate exploded")

    name = probe_tool("probe", parallel_safe=predicate)
    loop = _turn_with(delta("c1", name, '{"items": ["a"]}'))

    assert loop.registry.calls == [(name, {"items": ["a"]})]


def test_a_confirmation_callback_that_edits_its_preview_cannot_change_the_executed_call():
    """Preservation: the preview arguments are the callback's own copy.

    Only ``r`` is granted, so the write needs confirmation; the callback edits what it was shown and
    approves. The executed call still has the validated content.
    """

    def edit_the_preview_and_approve(name, arguments):
        arguments["content"] = "TAMPERED"
        arguments["operation"] = "TAMPERED"
        return "approve"

    callbacks = RecordingCallbacks(confirm=edit_the_preview_and_approve)
    loop = _turn_with(delta("c1", "file_editor", _WRITE), callbacks=callbacks, permissions={"r"})

    assert loop.registry.calls == [
        ("file_editor", {"file_path": "a.py", "operation": "write", "content": "x"})
    ]


def test_a_receiver_that_mutates_the_nested_arguments_it_is_shown_cannot_change_the_executed_call(
    probe_tool,
):
    """Preservation: ``on_tool_start`` gets the full arguments before execution.

    They are nested, so a shallow copy would let this mutation through to the call that runs.
    """

    def mutate_the_nested_arguments(call_id, name, arguments):
        for item in arguments.get("items", []):
            item["a"] = "TAMPERED"
            item["inner"].append("TAMPERED")

    callbacks = RecordingCallbacks(raises={"on_tool_start": mutate_the_nested_arguments})
    name = probe_tool("probe")
    loop = _turn_with(
        delta("c1", name, '{"items": [{"a": 1, "inner": [1, 2]}]}'), callbacks=callbacks
    )

    assert loop.registry.calls == [(name, {"items": [{"a": 1, "inner": [1, 2]}]})]


# -- Called directly: the batch and the executor build the parse themselves ---------------------------------


def _call(arguments: str) -> _ToolCall:
    return _ToolCall(id="c1", function=_FunctionCall(name="read_file", arguments=arguments))


def test_a_direct_batch_parses_its_own_calls():
    """Preservation: ``_execute_tool_calls`` called without a parse of its own still runs the call."""
    loop = make_loop(ScriptedProvider([chunk(content="unused")]))

    asyncio.run(loop._execute_tool_calls([_call('{"file_path": "a.py"}')]))

    assert loop.registry.calls == [("read_file", {"file_path": "a.py"})]


def test_the_executor_called_directly_parses_its_own_call():
    """Preservation: ``_exec_tool_async(tc)`` called directly, as ``test_runtime_wiring.py`` does."""
    loop = make_loop(ScriptedProvider([chunk(content="unused")]))

    result = asyncio.run(loop._exec_tool_async(_call('{"file_path": "a.py"}')))

    assert (result["result"], loop.registry.calls) == ("ok", [("read_file", {"file_path": "a.py"})])


# -- Step 25: isolation covers every depth the parser accepts (Codex #7) --------------------------------------

_NESTING = 520
_DEEP = '{"a": ' * _NESTING + "1" + "}" * _NESTING


def _depth(value) -> int:
    """How deeply dicts and lists nest in ``value``, counted without recursion."""
    deepest, stack = 0, [(value, 1)]
    while stack:
        node, level = stack.pop()
        if isinstance(node, dict):
            deepest = max(deepest, level)
            stack.extend((child, level + 1) for child in node.values())
        elif isinstance(node, list):
            deepest = max(deepest, level)
            stack.extend((child, level + 1) for child in node)
    return deepest


def _a_call_with_520_nested_objects(probe_tool):
    """Codex's probe: a registered read-only tool called with an object that holds 520 nested JSON
    objects. ``json.loads`` accepts that depth, and main ran the call once."""
    name = probe_tool("probe")
    loop = _turn_with(delta("c1", name, _DEEP))
    return name, loop


def test_a_call_with_deeply_nested_arguments_runs_once(probe_tool):
    """Baseline regression, Codex #7: the argument copy raises ``RecursionError`` before dispatch
    today, so the call never runs (zero executions)."""
    _, loop = _a_call_with_520_nested_objects(probe_tool)

    assert len(loop.registry.calls) == 1


def test_a_call_with_deeply_nested_arguments_runs_with_all_of_them(probe_tool):
    """Baseline regression, Codex #7: nothing reaches the tool today."""
    _, loop = _a_call_with_520_nested_objects(probe_tool)

    assert [_depth(arguments) for _, arguments in loop.registry.calls] == [_NESTING]


def test_a_call_with_deeply_nested_arguments_gets_its_own_result(probe_tool):
    """Baseline regression, Codex #7: its tool message is the cancelled text today."""
    _, loop = _a_call_with_520_nested_objects(probe_tool)

    assert [m["content"] for m in tool_messages(loop)] == ["ok"]


def test_a_call_with_deeply_nested_arguments_does_not_fail_the_turn(probe_tool):
    """Baseline regression, Codex #7: the turn ends ``failed``/``tools`` today. After: the call
    ran and a final text reply completes the turn, as on main."""
    _, loop = _a_call_with_520_nested_objects(probe_tool)

    assert (loop.outcome.status, loop.outcome.stage) == ("completed", None)


class _Opaque:
    """A value that is not a JSON type, as a provider that hands over dict arguments might pass."""

    def __init__(self, label: str) -> None:
        self.label = label

    def __eq__(self, other) -> bool:
        return isinstance(other, _Opaque) and other.label == self.label

    __hash__ = None  # type: ignore[assignment]


def test_dict_arguments_with_values_that_are_not_json_copy_as_they_always_did():
    """Preservation: a tuple, a set and an object of a class of the provider's own still copy.

    Every container is a new object, the opaque object is copied, and the values are equal.
    """
    arguments = {"t": (1, [2]), "s": {1, 2}, "o": _Opaque("x"), "d": {"n": [1, {"m": 2}]}}
    parsed = _ParsedCall.of(arguments)

    copied = parsed.arguments()

    assert copied == arguments
    assert copied["t"][1] is not arguments["t"][1]
    assert copied["o"] is not arguments["o"]
    assert copied["d"]["n"][1] is not arguments["d"]["n"][1]


def test_copies_keep_shared_and_circular_references_as_deepcopy_did():
    """Preservation: a list used twice stays one list in the copy, and a cycle stays a cycle."""
    shared: list = [1]
    arguments: dict = {"a": shared, "b": shared}
    arguments["self"] = arguments
    parsed = _ParsedCall.of(arguments)

    copied = parsed.arguments()

    assert copied["a"] is copied["b"] and copied["a"] is not shared
    assert copied["self"] is copied and copied is not arguments


def test_a_copy_is_independent_of_the_parse_and_of_the_other_copies():
    """Preservation: each consumer's copy is its own, at any depth it can mutate."""
    parsed = _ParsedCall.of('{"items": [{"a": [1, 2]}]}')
    first, second = parsed.arguments(), parsed.arguments()

    first["items"][0]["a"].append("TAMPERED")

    assert second == {"items": [{"a": [1, 2]}]} and parsed.args == {"items": [{"a": [1, 2]}]}
