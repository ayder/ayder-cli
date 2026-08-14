"""Agent severity, asserted on the production call path."""
import asyncio

import pytest

# scripts/ is on sys.path via tests/conftest.py (§C15).
from logging_gates import BATCHES, collect, resolve  # noqa: E402

from ayder_cli.agents.callbacks import AgentCallbacks


def _cb():
    return AgentCallbacks("demo", 7, asyncio.Event())


def test_tool_complete_is_trace_on_the_production_path(loguru_caplog):
    """It carries a result excerpt, one per tool call -> TRACE."""
    _cb().on_tool_complete("call-1", "the result")
    hits = [r for r in loguru_caplog.records
            if r["message"].startswith("agent tool_complete:")]
    assert hits, "tool_complete record never emitted"
    assert hits[0]["level"].name == "TRACE"
    assert hits[0]["extra"]["channel"] == "agent"


def test_tool_complete_does_not_leak_raw_result_content(loguru_caplog):
    """The TRACE record must carry only the result's length, never the
    result content itself -- not even truncated. Regression for the
    agents/callbacks.py:82 leak found in security review: `result[:200]`
    truncates but still emits up to 200 raw characters, and truncation is
    not redaction. Supersedes the old bounded-excerpt assertion, whose
    premise (a truncated preview is safe) is exactly what was wrong."""
    secret = "sk-proj-SENTINEL-DO-NOT-LOG-1234567890"
    result = f"tool output containing {secret}"

    _cb().on_tool_complete("call-1", result)

    hits = [r for r in loguru_caplog.records
            if r["message"].startswith("agent tool_complete:")]
    assert hits, "tool_complete record never emitted"
    hit = hits[0]
    assert hit["level"].name == "TRACE"
    assert hit["extra"]["channel"] == "agent"
    assert str(len(result)) in hit["message"], "expected the result length to be logged"
    assert secret not in hit["message"]
    assert secret not in loguru_caplog.text


def test_token_usage_is_debug_and_fires_once_per_turn(loguru_caplog):
    """Its only production call site is ChatLoop.run, after the stream."""
    _cb().on_token_usage(1234)
    hits = [r for r in loguru_caplog.records
            if r["message"].startswith("agent token_usage:")]
    assert len(hits) == 1
    assert hits[0]["level"].name == "DEBUG"


def test_token_usage_has_exactly_one_production_call_site():
    """Guards the premise of the row above: if someone starts calling this
    per-chunk, the DEBUG ruling stops being correct and this test says so."""
    import ast

    from logging_gates import SRC as src          # root derived from __file__
    sites = []
    for p in src.rglob("*.py"):
        for node in ast.walk(ast.parse(p.read_text())):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "on_token_usage"):
                sites.append(str(p.relative_to(src)))     # path only — §C14
    assert sites == ["loops/chat_loop.py"], sites


def test_tool_start_is_debug(loguru_caplog):
    _cb().on_tool_start("call-1", "bash", {"command": "echo hi"})
    hits = [r for r in loguru_caplog.records
            if r["message"].startswith("agent tool_start:")]
    assert hits and hits[0]["level"].name == "DEBUG"


def test_no_error_records_on_a_successful_callback_sequence(loguru_caplog):
    cb = _cb()
    cb.on_tool_start("c", "bash", {})
    cb.on_tool_complete("c", "ok")
    cb.on_token_usage(10)
    assert loguru_caplog.at_level("ERROR").messages == []


# --- AST assertion: supplements the production tests, never replaces them ---

EXPECTED = {
    "agents/callbacks.py :: AgentCallbacks.on_tool_complete :: agent tool_complete:": "trace",
    "agents/callbacks.py :: AgentCallbacks.on_token_usage :: agent token_usage:": "debug",
    "agents/callbacks.py :: AgentCallbacks.on_tool_start :: agent tool_start:": "debug",
    "agents/runner.py :: AgentRunner.run :: run started: agent=": "info",
    "agents/runner.py :: AgentRunner.run :: run completed: agent=": "info",
    "agents/runner.py :: AgentRunner.run :: run failed (captured via on_system_message):": "error",
    "agents/runner.py :: AgentRunner.run :: run vacuous: agent=": "error",
    "agents/registry.py :: AgentRegistry.create_run :: agent dispatch: run #": "debug",
    "tui/app.py :: AyderApp._maybe_nudge :: agent nudge:": "debug",
}


@pytest.mark.parametrize("identity,level", sorted(EXPECTED.items()))
def test_frozen_levels(identity, level):
    assert resolve(identity, collect(BATCHES["agents-tui"]))["level"] == level
