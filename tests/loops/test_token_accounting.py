"""Token accounting warns and carries on (plan step 9, D4).

The loop adds the provider's ``total_tokens`` to its running total and tells the context manager.
Before this step a usage value that was not a mapping made ``.get`` raise, a string total raised,
a negative total shrank the count, ``True`` counted as 1, a falsy usage (``{}``, ``[]``, ``False``)
counted as absent, and a raising ``update_from_response`` failed the turn. Now usage that is not
a mapping, or whose ``total_tokens`` is present but not a non-negative ``int`` (a ``bool`` does
not count), is treated as missing: the loop's own estimate is added, ``update_from_response`` is
skipped and one warning is logged. Absent usage (None) still means "no usage". A mapping without
``total_tokens`` adds 0 and still reaches ``update_from_response``, and a raising
``update_from_response`` is one guard warning.

Kind: baseline regression unless a docstring says preservation. Environment: local-faked (no
network; the provider, callbacks and context are the fakes in ``turn_fakes``). Layer: unit.

Every usage value is a provider chunk shape, so every case is a real input. The reply is 40
characters, so the loop's estimate is 10 tokens. Each red test asserts one claim.
"""

from __future__ import annotations

import pytest

from ayder_cli.loops.chat_loop import TurnOutcome
from tests.loops.turn_fakes import (
    FakeContext,
    RecordingCallbacks,
    ScriptedProvider,
    chunk,
    make_loop,
    run_turn,
)

_ESTIMATE = 10  # len("x" * 40) // 4


def _turn(usage, *, context: FakeContext | None = None):
    """Run one text turn whose chunk carries ``usage``; return the loop and its context."""
    context = context or FakeContext()
    loop = make_loop(ScriptedProvider([chunk(content="x" * 40, usage=usage)]), context=context)
    run_turn(loop)
    return loop, context


def _totals(loop) -> list[int]:
    """What ``on_token_usage`` was told, in order."""
    return [args[0] for _, args in loop.cb.of("on_token_usage")]


def _malformed_warnings(caplog) -> list[str]:
    return [m for m in caplog.only("warning").messages if "Provider usage is malformed" in m]


# Usage the loop cannot use, with the class name the warning shows.
_MALFORMED = [
    pytest.param("lots", "str", id="string"),
    pytest.param({"total_tokens": -5}, "dict", id="negative"),
    pytest.param({"total_tokens": "12"}, "dict", id="string-total"),
    pytest.param([], "list", id="empty-list"),
    pytest.param(False, "bool", id="false"),
    pytest.param({"total_tokens": True}, "dict", id="bool-total"),
]


# -- Malformed usage counts as missing ------------------------------------------


@pytest.mark.parametrize(
    "usage",
    [
        pytest.param("lots", id="string"),
        pytest.param({"total_tokens": -5}, id="negative"),
        pytest.param({"total_tokens": "12"}, id="string-total"),
        pytest.param({"total_tokens": True}, id="bool-total"),
    ],
)
def test_malformed_usage_adds_the_estimate(usage):
    """Baseline regression: today a string or a string total fails the turn, a negative total
    shrinks the count and ``True`` adds 1. After: the estimate is added and reported."""
    loop, _ = _turn(usage)

    assert _totals(loop) == [_ESTIMATE]


@pytest.mark.parametrize(("usage", "type_name"), _MALFORMED)
def test_malformed_usage_logs_one_warning(usage, type_name, loguru_caplog):
    """Baseline regression: no warning is logged today. After: one, naming the value's class."""
    _turn(usage)

    assert _malformed_warnings(loguru_caplog) == [
        f"Provider usage is malformed ({type_name}); using the estimate"
    ]


@pytest.mark.parametrize(
    "usage",
    [
        pytest.param({"total_tokens": -5}, id="negative"),
        pytest.param({"total_tokens": True}, id="bool-total"),
    ],
)
def test_malformed_usage_is_not_given_to_the_context_manager(usage):
    """Baseline regression: a malformed mapping reaches ``update_from_response`` today."""
    _, context = _turn(usage)

    assert context.usage == []


@pytest.mark.parametrize(
    "usage", [pytest.param("lots", id="string"), pytest.param({"total_tokens": "12"}, id="string-total")]
)
def test_malformed_usage_does_not_fail_the_turn(usage):
    """Baseline regression: a string usage or string total raises in accounting today."""
    loop, _ = _turn(usage)

    assert loop.outcome == TurnOutcome("completed")


# -- Absent means None -------------------------------------------------------------


def test_an_empty_mapping_adds_zero():
    """Baseline regression: ``{}`` is falsy, so today it counts as absent and adds the estimate."""
    loop, _ = _turn({})

    assert _totals(loop) == [0]


def test_an_empty_mapping_reaches_the_context_manager():
    """Baseline regression: ``{}`` counts as absent today, so the manager is not called."""
    _, context = _turn({})

    assert context.usage == [{}]


# -- A raising update_from_response ---------------------------------------------------


def _accounting_raises(usage=None):
    context = FakeContext(raises={"update_from_response": RuntimeError("accounting exploded")})
    return _turn(usage if usage is not None else {"total_tokens": 5}, context=context)


def test_a_raising_update_from_response_does_not_fail_the_turn():
    """Baseline regression, E12: the turn is ``failed``/``context`` today. After: ``completed``."""
    loop, _ = _accounting_raises()

    assert loop.outcome == TurnOutcome("completed")


def test_a_raising_update_from_response_is_one_guard_warning(loguru_caplog):
    """Baseline regression, E12: nothing is logged as a warning today."""
    _accounting_raises()

    warnings = [m for m in loguru_caplog.only("warning").messages if "raised; continuing" in m]
    assert warnings == ["token accounting raised; continuing without it"]


def test_a_raising_update_from_response_keeps_the_reported_total():
    """Baseline regression, E12: the turn fails before it reports the total today.

    The reported tokens were already added, so ``on_token_usage`` is told 5.
    """
    loop, _ = _accounting_raises()

    assert _totals(loop) == [5]


# -- What does not change (preservation) -------------------------------------------------


@pytest.mark.parametrize(
    ("usage", "total"),
    [
        pytest.param({"total_tokens": 7}, 7, id="reported"),
        pytest.param({"total_tokens": 0}, 0, id="reported-zero"),
        pytest.param({"prompt_tokens": 100, "completion_tokens": 5}, 0, id="no-total-tokens"),
        pytest.param(None, _ESTIMATE, id="absent"),
        pytest.param([], _ESTIMATE, id="empty-list"),
        pytest.param(False, _ESTIMATE, id="false"),
    ],
)
def test_the_reported_total_or_the_estimate_is_what_the_user_is_told(usage, total):
    """Preservation: a valid total is added as reported, a mapping without ``total_tokens`` adds 0
    (the Ollama manager's case), and absent or falsy non-mapping usage is the estimate. Passes
    before and after."""
    loop, _ = _turn(usage)

    assert _totals(loop) == [total]


@pytest.mark.parametrize(
    "usage",
    [
        pytest.param({"total_tokens": 7}, id="reported"),
        pytest.param({"prompt_tokens": 100, "completion_tokens": 5}, id="no-total-tokens"),
    ],
)
def test_usable_usage_reaches_the_context_manager(usage):
    """Preservation: usage the loop can use is given to ``update_from_response``, unchanged."""
    _, context = _turn(usage)

    assert context.usage == [usage]
