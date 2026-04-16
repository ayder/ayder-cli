"""Regression: DefaultContextManager.should_compact must use provider-reported
tokens when available.

Opus47 finding #6: should_compact delegated to should_trigger_summarization
which uses TokenCounter estimates — under-counts JSON/tool payloads,
compaction triggers too late.
"""
from unittest.mock import MagicMock

from ayder_cli.core.default_context_manager import DefaultContextManager


def _make_config(max_context_tokens=8192):
    cfg = MagicMock()
    cfg.context_manager.max_context_tokens = max_context_tokens
    cfg.context_manager.reserve_ratio = 0.3
    cfg.context_manager.compaction_threshold = 0.7
    cfg.context_manager.tool_result_compress_age = 5
    cfg.context_manager.max_tool_result_length = 2048
    cfg.context_manager.compress_tool_results = True
    cfg.context_manager.enabled = True
    cfg.provider = "openai"
    cfg.model = "gpt-4o"
    return cfg


def test_should_compact_uses_real_prompt_tokens_when_available():
    """When update_from_response has been called, real tokens drive the decision."""
    mgr = DefaultContextManager.from_config(_make_config(max_context_tokens=10_000))

    # No messages — estimator would say 0 used → never compact.
    # But real prompt tokens = 8000 → over 0.7 * 10000 = 7000 → should compact.
    mgr.update_from_response({"prompt_tokens": 8_000, "completion_tokens": 50})

    assert mgr.should_compact() is True, \
        "should_compact must use _last_prompt_tokens (provider-reported) over estimator"


def test_should_compact_false_when_real_tokens_below_threshold():
    mgr = DefaultContextManager.from_config(_make_config(max_context_tokens=10_000))
    mgr.update_from_response({"prompt_tokens": 4_000, "completion_tokens": 50})
    # 4000 < 7000 threshold
    assert mgr.should_compact() is False


def test_should_compact_falls_back_to_estimator_without_real_tokens():
    """Before update_from_response is ever called, the estimator fallback applies."""
    mgr = DefaultContextManager.from_config(_make_config(max_context_tokens=200))
    # Prepare a large history so the estimator crosses threshold
    messages = [{"role": "system", "content": "S"}]
    for i in range(50):
        messages.append({"role": "user", "content": "x" * 200})
    mgr.prepare_messages(messages)

    # No update_from_response — _last_prompt_tokens is still 0
    # The estimator path is the only one available here
    assert mgr.should_compact() is True
