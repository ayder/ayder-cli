"""Structured events must come out of the real call sites, not a stub.

Every test here drives a production method and then reads what landed in
trace.jsonl. None of them calls ``emit_event`` directly: an emitter that was
never wired into ``ChatLoop``/the context managers/``AgentRegistry`` must make
these fail.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from loguru import logger

from ayder_cli.agents.config import AgentConfig
from ayder_cli.agents.registry import AgentRegistry
from ayder_cli.agents.runner import AgentRunOutcome
from ayder_cli.core.default_context_manager import DefaultContextManager
from ayder_cli.core.ollama_context_manager import OllamaContextManager
from ayder_cli.logging_config import LoggingSettings, setup_logging
from ayder_cli.loops.chat_loop import ChatLoop, ChatLoopConfig

# The correlation envelope every event carries (C11 + R-3). `run_id` is NOT in
# it: parent-loop events must omit the key entirely rather than serialise None.
ENVELOPE = {"channel", "evt", "schema_version", "session_id"}

ITERATION_FIELDS = {"n", "model", "content_len", "reasoning_len",
                    "tool_calls", "hist_tokens", "ms"}
TOOL_CALL_FIELDS = {"name", "args_len", "ms", "ok", "err_type"}
CONTEXT_TRIM_FIELDS = {"before", "after", "dropped", "strategy"}
AGENT_RUN_FIELDS = {"agent", "run_id", "status", "secs"}
STRATEGIES = {"compaction", "max_history", "token_budget", "budget_exhausted"}

SESSION = "feedfacecafe"


# --- harness ---------------------------------------------------------------


class _Chunk:
    """Minimal stream chunk that ChatLoop understands."""

    def __init__(self, content="", reasoning="", tool_calls=None, usage=None):
        self.content = content
        self.reasoning = reasoning
        self.tool_calls = tool_calls or []
        self.usage = usage


class _ToolCallChunk:
    """Shape expected by the ChatLoop inner loop (matches providers.base)."""

    def __init__(self, call_id, name, arguments):
        self.id = call_id
        self.name = name
        self.arguments = arguments
        self._stream_index = 0


class _Callbacks:
    """Terminates the loop after `cancel_after` is_cancelled() polls."""

    def __init__(self, cancel_after=4):
        self._n = 0
        self._cancel_after = cancel_after

    def on_thinking_start(self): pass
    def on_thinking_stop(self): pass
    def on_assistant_content(self, text): pass
    def on_thinking_content(self, text): pass
    def on_token_usage(self, total_tokens): pass
    def on_tool_start(self, call_id, name, arguments): pass
    def on_tool_complete(self, call_id, result): pass
    def on_tools_cleanup(self): pass
    def on_system_message(self, text): pass

    async def request_confirmation(self, name, arguments):
        approval = MagicMock()
        approval.action = "approve"
        return approval

    def is_cancelled(self):
        self._n += 1
        return self._n > self._cancel_after


def _setup(tmp_path: Path) -> None:
    setup_logging(LoggingSettings(
        level="NONE", trace_enabled=True,
        file_path=str(tmp_path / "a.log"),
        error_path=str(tmp_path / "e.log"),
        trace_path=str(tmp_path / "t.jsonl"),
    ))


def _events(tmp_path: Path, evt: str) -> list[dict]:
    logger.complete()
    p = tmp_path / "t.jsonl"
    if not p.exists():
        return []
    out = []
    for line in p.read_text().splitlines():
        if not line.strip():
            continue
        extra = json.loads(line)["record"]["extra"]
        if extra.get("evt") == evt:
            out.append(extra)
    return out


def _text_only_provider():
    class _P:
        async def stream_with_tools(self, messages, model, tools, options, verbose):
            yield _Chunk(content="Done.",
                         usage={"total_tokens": 20, "prompt_tokens": 15,
                                "completion_tokens": 5})
    return _P()


def _tool_then_text_provider(tool_name, arguments='{}'):
    class _P:
        def __init__(self):
            self._turn = 0

        async def stream_with_tools(self, messages, model, tools, options, verbose):
            if self._turn == 0:
                self._turn += 1
                yield _Chunk(tool_calls=[_ToolCallChunk("call_1", tool_name, arguments)],
                             usage={"total_tokens": 10})
            else:
                yield _Chunk(content="Done.", usage={"total_tokens": 20})
    return _P()


def _loop(provider, tool_name="search_codebase", fake_result="ok", cancel_after=4,
          run_id=None):
    registry = MagicMock()
    registry.get_schemas.return_value = [
        {"type": "function", "function": {"name": tool_name, "parameters": {}}}
    ]
    registry.execute.return_value = fake_result
    return ChatLoop(
        llm=provider, registry=registry, messages=[{"role": "system", "content": "t"}],
        config=ChatLoopConfig(permissions={"r", "w", "x"}, session_id=SESSION,
                              run_id=run_id),
        callbacks=_Callbacks(cancel_after=cancel_after),
    )


# --- iteration -------------------------------------------------------------


@pytest.mark.anyio
async def test_text_only_turn_emits_one_iteration_event(tmp_path):
    _setup(tmp_path)
    await _loop(_text_only_provider()).run()

    events = _events(tmp_path, "iteration")
    assert len(events) == 1
    e = events[0]
    assert set(e) == ENVELOPE | ITERATION_FIELDS, "no field outside the frozen set"
    assert e["session_id"] == SESSION
    assert e["channel"] == "llm"
    assert e["n"] == 1
    assert e["tool_calls"] == 0
    assert e["content_len"] == len("Done.")
    assert e["reasoning_len"] == 0
    assert e["hist_tokens"] == 20
    assert isinstance(e["ms"], int)


@pytest.mark.anyio
async def test_parent_loop_iteration_omits_run_id_entirely(tmp_path):
    """A parent CLI/TUI loop has no run; the key must be absent, not None."""
    _setup(tmp_path)
    await _loop(_text_only_provider()).run()

    events = _events(tmp_path, "iteration")
    assert events
    assert all("run_id" not in e for e in events)


@pytest.mark.anyio
async def test_pre_request_cancellation_emits_no_iteration_event(tmp_path):
    """No request was sent, so there is no iteration to describe."""
    _setup(tmp_path)
    await _loop(_text_only_provider(), cancel_after=0).run()

    assert _events(tmp_path, "iteration") == []


@pytest.mark.anyio
async def test_mid_stream_cancellation_still_emits_an_iteration_event(tmp_path):
    """The `finally:` must cover the early returns that happen after the request."""
    _setup(tmp_path)
    await _loop(_tool_then_text_provider("search_codebase"), cancel_after=1).run()

    events = _events(tmp_path, "iteration")
    assert len(events) == 1, "a turn cancelled after the request is still an iteration"
    assert set(events[0]) == ENVELOPE | ITERATION_FIELDS


# --- tool_call -------------------------------------------------------------


@pytest.mark.anyio
async def test_auto_approved_tool_emits_a_tool_call_event(tmp_path):
    """The `_exec_tool_async` path: exec_result is unwrapped to a dict there,
    so the event has to be emitted before the unwrap."""
    _setup(tmp_path)
    await _loop(_tool_then_text_provider("search_codebase", '{"pattern": "x"}'),
                fake_result="hits").run()

    tools = _events(tmp_path, "tool_call")
    assert len(tools) == 1
    e = tools[0]
    assert set(e) == ENVELOPE | TOOL_CALL_FIELDS, "no field outside the frozen set"
    assert e["channel"] == "tool"
    assert e["name"] == "search_codebase"
    assert e["session_id"] == SESSION
    assert e["ok"] is True
    assert e["err_type"] is None
    assert e["args_len"] == len(str({"pattern": "x"}))
    assert isinstance(e["ms"], int)

    iters = _events(tmp_path, "iteration")
    assert len(iters) == 2
    assert any(i["tool_calls"] == 1 for i in iters)


@pytest.mark.anyio
async def test_needs_confirmation_tool_emits_a_tool_call_event(tmp_path):
    """The second execution path: an approved confirmation calls the policy
    directly, so it needs its own emission — one helper, two call sites."""
    _setup(tmp_path)
    # `fetch_web` requires the "http" permission, which {r,w,x} does not grant,
    # so ExecutionPolicy routes it to the confirmation branch.
    await _loop(_tool_then_text_provider("fetch_web",
                                         '{"url": "https://example.com"}'),
                tool_name="fetch_web", fake_result="page").run()

    tools = _events(tmp_path, "tool_call")
    assert len(tools) == 1, "the needs-confirmation branch must emit too"
    e = tools[0]
    assert set(e) == ENVELOPE | TOOL_CALL_FIELDS
    assert e["name"] == "fetch_web"
    assert e["ok"] is True
    assert e["err_type"] is None


@pytest.mark.anyio
async def test_rejected_tool_records_ok_false_and_a_real_err_type(tmp_path):
    """`ok` must be read from ExecutionResult, not from the unwrapped dict.

    `read_file` with a non-string `file_path` clears the loop's own
    required-argument screen (the value is present and not blank) and is then
    refused by ValidationAuthority inside `execute_with_registry` — the case
    `ok`/`err_type` genuinely cover.
    """
    _setup(tmp_path)
    await _loop(_tool_then_text_provider("read_file", '{"file_path": 123}'),
                tool_name="read_file").run()

    events = _events(tmp_path, "tool_call")
    assert len(events) == 1
    assert events[0]["ok"] is False
    assert events[0]["err_type"] == "ValidationError"


# --- agent-shaped correlation ---------------------------------------------


@pytest.mark.anyio
async def test_agent_loop_events_carry_the_inherited_run_id(tmp_path):
    """An agent's loop shares the parent session id and adds its own run id."""
    _setup(tmp_path)
    await _loop(_tool_then_text_provider("search_codebase", '{"pattern": "x"}'),
                run_id=7).run()

    iters = _events(tmp_path, "iteration")
    tools = _events(tmp_path, "tool_call")
    assert iters and tools
    for e in iters:
        assert set(e) == ENVELOPE | ITERATION_FIELDS | {"run_id"}
        assert e["session_id"] == SESSION
        assert e["run_id"] == 7
    for e in tools:
        assert set(e) == ENVELOPE | TOOL_CALL_FIELDS | {"run_id"}
        assert e["run_id"] == 7


# --- context_trim ----------------------------------------------------------


def _msgs(n, content="hello world "):
    return ([{"role": "system", "content": "sys"}]
            + [{"role": "user", "content": content * 20} for _ in range(n)])


def _default_manager(max_context_tokens=8192):
    """Same shape tests/core/test_default_context_manager.py already uses."""
    cfg = MagicMock()
    cfg.model = "unknown"
    cfg.provider = "ollama"          # keeps TokenCounter on char estimates
    cfg.num_ctx = max_context_tokens
    cfg.context_manager.enabled = True
    cfg.context_manager.max_context_tokens = max_context_tokens
    cfg.context_manager.reserve_ratio = 0.3
    cfg.context_manager.compaction_threshold = 0.7
    cfg.context_manager.tool_result_compress_age = 5
    cfg.context_manager.max_tool_result_length = 2048
    cfg.context_manager.compress_tool_results = True
    cfg.context_manager.enable_compression = False
    m = DefaultContextManager.from_config(cfg)
    m.session_id = SESSION
    return m


def _ollama_manager(provisional_context_length=1_000_000, compaction_threshold=0.7):
    m = OllamaContextManager(
        provisional_context_length=provisional_context_length,
        reserve_ratio=0.3,
        compaction_threshold=compaction_threshold,
    )
    m.session_id = SESSION
    m.freeze_system_prompt("sys", [])
    return m


def test_default_manager_max_history_emits_one_trim_event(tmp_path):
    _setup(tmp_path)
    m = _default_manager()
    messages = _msgs(20)
    out = m.prepare_messages(messages, max_history=4)

    events = [e for e in _events(tmp_path, "context_trim")
              if e["strategy"] == "max_history"]
    assert len(events) == 1, "the count cap must produce exactly one event"
    e = events[0]
    assert set(e) == ENVELOPE | CONTEXT_TRIM_FIELDS, "no field outside the frozen set"
    assert e["channel"] == "context"
    assert e["session_id"] == SESSION
    assert e["dropped"] == e["before"] - e["after"] > 0
    assert len(out) < len(messages)


def test_default_manager_token_budget_emits_token_budget_not_max_history(tmp_path):
    """A budget-driven trim is NOT a max_history trim; the label must differ."""
    _setup(tmp_path)
    m = _default_manager(max_context_tokens=600)      # tiny budget, no count cap
    m.prepare_messages(_msgs(40), max_history=0)

    events = _events(tmp_path, "context_trim")
    strategies = {e["strategy"] for e in events}
    assert "token_budget" in strategies
    assert "max_history" not in strategies
    budget = [e for e in events if e["strategy"] == "token_budget"]
    assert len(budget) == 1
    assert budget[0]["dropped"] == budget[0]["before"] - budget[0]["after"] > 0


def test_default_manager_exhausted_budget_emits_budget_exhausted(tmp_path):
    """`available <= 0` drops all history before the normal emission point."""
    _setup(tmp_path)
    m = _default_manager(max_context_tokens=8192)
    m.freeze_system_prompt("x" * 200_000, [])         # overhead eats the budget
    m.prepare_messages(_msgs(10), max_history=0)

    events = [e for e in _events(tmp_path, "context_trim")
              if e["strategy"] == "budget_exhausted"]
    assert len(events) == 1
    assert set(events[0]) == ENVELOPE | CONTEXT_TRIM_FIELDS
    assert events[0]["after"] <= 1
    assert events[0]["dropped"] == events[0]["before"] - events[0]["after"] > 0


def test_default_manager_no_trim_emits_nothing(tmp_path):
    """An operation that drops nothing must stay silent."""
    _setup(tmp_path)
    m = _default_manager()
    m.prepare_messages(_msgs(3), max_history=0)

    assert _events(tmp_path, "context_trim") == []


def test_ollama_max_history_emits_a_trim_event(tmp_path):
    _setup(tmp_path)
    m = _ollama_manager()
    m.prepare_messages(_msgs(20), max_history=4)

    events = [e for e in _events(tmp_path, "context_trim")
              if e["strategy"] == "max_history"]
    assert len(events) == 1, "Ollama trimming must emit too — it is a different class"
    assert set(events[0]) == ENVELOPE | CONTEXT_TRIM_FIELDS
    assert events[0]["session_id"] == SESSION
    assert events[0]["dropped"] == events[0]["before"] - events[0]["after"] > 0


def test_ollama_compaction_emits_a_compaction_event(tmp_path):
    """Compaction and trimming are separate operations and separate events."""
    _setup(tmp_path)
    m = _ollama_manager(provisional_context_length=500, compaction_threshold=0.1)
    # should_compact() reads Ollama's REAL prompt token count, which is 0 until
    # a response has been ingested — without this the compaction path is dead.
    m.update_from_response({"prompt_tokens": 400})
    m.prepare_messages(_msgs(40), max_history=0)

    events = [e for e in _events(tmp_path, "context_trim")
              if e["strategy"] == "compaction"]
    assert len(events) == 1
    assert set(events[0]) == ENVELOPE | CONTEXT_TRIM_FIELDS
    assert events[0]["dropped"] == events[0]["before"] - events[0]["after"] > 0


def test_manager_trim_carries_run_id_only_for_an_agent_loop(tmp_path):
    """Same conditional envelope as the loop events: absent for a parent."""
    _setup(tmp_path)
    parent = _default_manager()
    parent.prepare_messages(_msgs(20), max_history=4)
    agent = _ollama_manager()
    agent.run_id = 7
    agent.prepare_messages(_msgs(20), max_history=4)

    events = _events(tmp_path, "context_trim")
    assert len(events) == 2
    with_run = [e for e in events if "run_id" in e]
    assert len(with_run) == 1
    assert with_run[0]["run_id"] == 7
    assert set(with_run[0]) == ENVELOPE | CONTEXT_TRIM_FIELDS | {"run_id"}


def test_every_reachable_strategy_is_one_of_the_frozen_four(tmp_path):
    """Drives all four labelled paths into one trace and pins the vocabulary."""
    _setup(tmp_path)
    _default_manager().prepare_messages(_msgs(20), max_history=4)      # max_history
    _default_manager(max_context_tokens=600).prepare_messages(         # token_budget
        _msgs(40), max_history=0)
    exhausted = _default_manager()
    exhausted.freeze_system_prompt("x" * 200_000, [])                  # budget_exhausted
    exhausted.prepare_messages(_msgs(10), max_history=0)
    compacting = _ollama_manager(provisional_context_length=500,
                                 compaction_threshold=0.1)             # compaction
    compacting.update_from_response({"prompt_tokens": 400})
    compacting.prepare_messages(_msgs(40), max_history=0)

    events = _events(tmp_path, "context_trim")
    assert {e["strategy"] for e in events} == STRATEGIES
    for e in events:
        assert e["strategy"] in STRATEGIES, f"unfrozen strategy {e['strategy']!r}"


# --- agent_run -------------------------------------------------------------


@pytest.mark.anyio
async def test_completed_agent_run_emits_agent_run_with_the_parent_session_id(tmp_path):
    """The event must exist AND carry the id of the session that spawned it."""
    _setup(tmp_path)
    registry = AgentRegistry(
        agents={"coder": AgentConfig(name="coder", system_prompt="You code.")},
        parent_config=MagicMock(),
        project_ctx=MagicMock(),
        process_manager=MagicMock(),
        permissions={"r"},
        agent_timeout=5,
        session_id=SESSION,
    )
    registry.set_loop(asyncio.get_running_loop())
    with patch("ayder_cli.agents.registry.AgentRunner") as MockRunner:
        MockRunner.return_value.agent_name = "coder"
        MockRunner.return_value.run = AsyncMock(
            return_value=AgentRunOutcome("done", "ok", None, None)
        )
        run_id = registry.create_run("coder", "write the tests")
        await registry._runs[run_id].done_event.wait()

    assert registry._runs[run_id].status == "done", "must reach a terminal status"

    events = _events(tmp_path, "agent_run")
    assert len(events) == 1
    e = events[0]
    assert set(e) == ENVELOPE | AGENT_RUN_FIELDS, "no field outside the frozen set"
    assert e["channel"] == "agent"
    assert e["session_id"] == SESSION, \
        "an agent's events must tie back to the turn that spawned them"
    assert e["agent"] == "coder"
    assert e["run_id"] == run_id
    assert e["status"] == "done"
    assert isinstance(e["secs"], int)
