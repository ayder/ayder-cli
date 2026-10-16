"""The newest unit survives an over-budget trim (finding F8).

``DefaultContextManager.prepare_messages`` stopped at the first unit from the
end that did not fit. When that was the newest unit (the request the model is
being asked to answer), the result was empty and the request was the system
prompt alone. The ``available <= 0`` branch did the same. The newest unit is
now always kept; when it fits, the output is exactly what it was before, so
the normal path's message prefix is unchanged.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from ayder_cli.core.default_context_manager import DefaultContextManager

MARKER = {"role": "user", "content": "[... history truncated for context efficiency ...]"}


def _manager(max_context_tokens: int = 1000) -> DefaultContextManager:
    cfg = MagicMock()
    cfg.model = "unknown"
    cfg.provider = "ollama"  # char-based token estimates, no tiktoken
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
    m.freeze_system_prompt("sys", [])
    return m


def _events(monkeypatch):
    seen: list[dict] = []
    monkeypatch.setattr(
        "ayder_cli.core.default_context_manager.emit_event",
        lambda channel, evt, **fields: seen.append(fields) if evt == "context_trim" else None,
    )
    return seen


def _small(n: int) -> list[dict]:
    out = [{"role": "system", "content": "sys"}]
    for i in range(n):
        out.append({"role": "user", "content": f"q{i}"})
        out.append({"role": "assistant", "content": f"a{i}"})
    return out


def test_oversized_newest_unit_is_kept():
    """Baseline regression: the request is the system prompt alone today."""
    history = _small(2) + [{"role": "user", "content": "please " + "x" * 6000}]
    out = _manager().prepare_messages(history)
    assert out == [history[0], history[-1]]


def test_exhausted_budget_keeps_newest_unit():
    """Baseline regression: available <= 0 drops every history message today."""
    m = _manager()
    m.freeze_system_prompt("x" * 200_000, [])
    history = _small(3) + [{"role": "user", "content": "the request"}]
    out = m.prepare_messages(history)
    assert out == [history[0], history[-1]]


def test_oversized_newest_unit_ignores_max_history():
    """Baseline regression: a 2-message newest unit exceeds max_history=1 and
    is dropped today."""
    unit = [
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "c1", "type": "function",
             "function": {"name": "read_file", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "c1", "name": "read_file", "content": "r"},
    ]
    history = _small(2) + unit
    out = _manager(100_000).prepare_messages(history, max_history=1)
    assert out == [history[0], MARKER, *unit]


def test_trim_event_fields_stay_truthful(monkeypatch):
    """Baseline regression: the event says the newest unit was dropped today.
    before/after/dropped describe what is sent; nothing dropped, no event."""
    seen = _events(monkeypatch)
    history = _small(2) + [{"role": "user", "content": "x" * 6000}]
    _manager().prepare_messages(history)
    assert seen == [{"before": 5, "after": 1, "dropped": 4,
                     "strategy": "token_budget", "session_id": None}]

    seen.clear()
    _manager().prepare_messages([history[0], history[-1]])
    assert seen == []


def test_in_budget_output_is_unchanged():
    """Preservation: a history that fits is returned exactly."""
    history = _small(5)
    out = _manager(100_000).prepare_messages(history)
    assert out == history
    assert [json.dumps(m) for m in out] == [json.dumps(m) for m in history]


def _reference_trim(m: DefaultContextManager, history: list[dict]) -> list[dict]:
    """The pre-fix greedy trim, for a history whose newest unit fits."""
    available = m._available_budget(m._system_tokens + m._schema_tokens)
    kept: list[dict] = []
    used = 0
    for msg in reversed(history[1:]):  # one-message units only
        cost = m._counter.count_messages([msg])
        if used + cost > available:
            break
        kept.insert(0, msg)
        used += cost
    if kept and kept[0]["role"] != "user":
        kept.insert(0, MARKER)
    return [history[0], *kept]


def test_normal_token_budget_trim_is_unchanged():
    """Preservation: when the newest unit fits, the trim is the same as before."""
    history = [{"role": "system", "content": "sys"}]
    for i in range(40):
        history.append({"role": "user" if i % 2 == 0 else "assistant",
                        "content": f"m{i} " + "x" * 120})
    m = _manager(1000)
    out = m.prepare_messages(history)
    assert len(out) < len(history)
    assert out == _reference_trim(_manager(1000), history)
