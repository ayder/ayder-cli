"""Tests for OllamaContextManager — cache-aware stable-prefix context management."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from ayder_cli.core.ollama_context_manager import OllamaContextManager, OllamaContextStats


def make_manager(ctx_length=65536, reserve=0.3, compaction=0.7):
    return OllamaContextManager(
        provisional_context_length=ctx_length,
        reserve_ratio=reserve,
        compaction_threshold=compaction,
    )


def test_implements_protocol():
    from ayder_cli.core.context_manager import ContextManagerProtocol
    mgr = make_manager()
    assert isinstance(mgr, ContextManagerProtocol)


def test_freeze_system_prompt():
    mgr = make_manager()
    mgr.freeze_system_prompt("You are helpful.", [{"type": "function"}])
    msgs = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Hi"},
    ]
    result = mgr.prepare_messages(msgs)
    assert result[0] == {"role": "system", "content": "You are helpful."}


def test_messages_are_append_only():
    """prepare_messages should never reorder messages."""
    mgr = make_manager(ctx_length=100000)
    mgr.freeze_system_prompt("System.", [])
    msgs = [
        {"role": "system", "content": "System."},
        {"role": "user", "content": "First"},
        {"role": "assistant", "content": "Response 1"},
        {"role": "user", "content": "Second"},
        {"role": "assistant", "content": "Response 2"},
    ]
    result = mgr.prepare_messages(msgs)
    roles = [m["role"] for m in result]
    assert roles == ["system", "user", "assistant", "user", "assistant"]
    assert result[1]["content"] == "First"
    assert result[3]["content"] == "Second"


def test_prefix_stability_across_calls():
    """Two consecutive calls with appended messages should share the same prefix."""
    mgr = make_manager(ctx_length=100000)
    mgr.freeze_system_prompt("System.", [])
    msgs1 = [
        {"role": "system", "content": "System."},
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there"},
    ]
    result1 = mgr.prepare_messages(msgs1)

    msgs2 = msgs1 + [
        {"role": "user", "content": "Follow up"},
        {"role": "assistant", "content": "Sure"},
    ]
    result2 = mgr.prepare_messages(msgs2)

    for i in range(len(result1)):
        assert result1[i] == result2[i], f"Prefix diverged at index {i}"


def test_compaction_triggers_on_threshold():
    """should_compact returns True when utilization exceeds threshold."""
    mgr = make_manager(ctx_length=1000, reserve=0.3, compaction=0.7)
    mgr.freeze_system_prompt("S", [])
    mgr.update_from_response({"prompt_tokens": 600, "completion_tokens": 50})
    assert mgr.should_compact() is True


def test_compaction_does_not_trigger_below_threshold():
    mgr = make_manager(ctx_length=1000, reserve=0.3, compaction=0.7)
    mgr.freeze_system_prompt("S", [])
    mgr.update_from_response({"prompt_tokens": 100, "completion_tokens": 10})
    assert mgr.should_compact() is False


def test_compaction_produces_summary_message():
    """After compaction, oldest messages should be replaced with a summary."""
    mgr = make_manager(ctx_length=500, reserve=0.3, compaction=0.5)
    mgr.freeze_system_prompt("System.", [])
    msgs = [{"role": "system", "content": "System."}]
    for i in range(10):
        msgs.append({"role": "user", "content": f"Question {i} " + "x" * 50})
        msgs.append({"role": "assistant", "content": f"Answer {i} " + "y" * 50})
    mgr.update_from_response({"prompt_tokens": 400, "completion_tokens": 20})
    result = mgr.prepare_messages(msgs)
    assert len(result) < len(msgs)
    assert result[0]["role"] == "system"
    has_summary = any("summary" in m.get("content", "").lower() for m in result)
    assert has_summary


def test_update_from_response_stores_real_tokens():
    mgr = make_manager()
    mgr.freeze_system_prompt("S", [])
    mgr.update_from_response({
        "prompt_tokens": 500,
        "completion_tokens": 100,
        "prompt_eval_ns": 5000000,
        "eval_ns": 2000000,
    })
    stats = mgr.get_stats()
    assert isinstance(stats, OllamaContextStats)
    assert stats.real_prompt_tokens == 500
    assert stats.real_completion_tokens == 100


def test_get_stats_returns_ollama_stats():
    mgr = make_manager(ctx_length=10000)
    mgr.freeze_system_prompt("S", [])
    stats = mgr.get_stats()
    assert isinstance(stats, OllamaContextStats)
    assert stats.actual_context_length == 10000


def test_from_config_classmethod():
    cfg = MagicMock()
    cfg.driver = "ollama"
    cfg.base_url = "http://localhost:11434"
    cfg.num_ctx = 32768
    cfg.context_manager.reserve_ratio = 0.25
    cfg.context_manager.compaction_threshold = 0.7
    mgr = OllamaContextManager.from_config(cfg)
    assert isinstance(mgr, OllamaContextManager)


def test_cache_monitor_integration():
    """update_from_response should feed timing data to CacheMonitor."""
    from ayder_cli.core.cache_monitor import CacheMonitor
    mgr = make_manager()
    mgr.freeze_system_prompt("S", [])
    mgr._cache_monitor = CacheMonitor()

    # First call — baseline (cold)
    mgr.update_from_response({
        "prompt_tokens": 100, "completion_tokens": 10,
        "prompt_eval_ns": 1_000_000, "eval_ns": 500_000,
    })
    assert mgr._cache_monitor.last_status.state == "cold"

    # Second call — much faster (hot)
    mgr.update_from_response({
        "prompt_tokens": 120, "completion_tokens": 15,
        "prompt_eval_ns": 100_000, "eval_ns": 600_000,
    })
    assert mgr._cache_monitor.last_status.state == "hot"


def test_adaptive_compaction_delays_when_hot():
    """When cache is hot, compaction threshold should increase to 0.90."""
    from ayder_cli.core.cache_monitor import CacheMonitor
    mgr = make_manager(ctx_length=1000, reserve=0.3, compaction=0.7)
    mgr.freeze_system_prompt("S", [])
    mgr._cache_monitor = CacheMonitor()

    # Establish baseline
    mgr.update_from_response({"prompt_tokens": 100, "prompt_eval_ns": 1_000_000})
    # Make cache hot
    mgr.update_from_response({"prompt_tokens": 550, "prompt_eval_ns": 50_000})

    # At 550/1000 = 78% utilization — would normally compact at 70%
    # But cache is hot, so threshold pushed to 90%
    assert mgr.should_compact() is False

    # Push to 91% — even hot cache must compact
    mgr.update_from_response({"prompt_tokens": 640, "prompt_eval_ns": 50_000})
    assert mgr.should_compact() is True


def test_first_call_captures_agent_prompts_appended_after_freeze():
    """System message modified AFTER freeze (e.g., agent prompts) must be captured.

    Regression test: freeze_system_prompt() is called in create_runtime() BEFORE
    agents are registered. Agent capability prompts are appended to messages[0]
    afterwards. The first prepare_messages() call must capture the full content
    and freeze it for KV-cache stability on all subsequent calls.
    """
    mgr = make_manager(ctx_length=100000)
    mgr.freeze_system_prompt("You are helpful.", [])

    # Simulate what TUI/CLI does: append agent prompts to messages[0] AFTER freeze
    full_prompt = "You are helpful.\n\n## Registered Agents\n- code_reviewer"
    messages = [
        {"role": "system", "content": full_prompt},
        {"role": "user", "content": "Hello"},
    ]
    result = mgr.prepare_messages(messages)

    # First call: agent prompt MUST survive
    assert "Registered Agents" in result[0]["content"]
    assert "code_reviewer" in result[0]["content"]


def test_frozen_prompt_stable_after_first_call():
    """After the first call finalizes the system prompt, it must be frozen for KV-cache.

    Even if someone mutates messages[0] later, prepare_messages must return
    the frozen content — not the mutated version.
    """
    mgr = make_manager(ctx_length=100000)
    mgr.freeze_system_prompt("Base prompt.", [])

    full_prompt = "Base prompt.\n\n## Registered Agents\n- code_reviewer"
    messages = [
        {"role": "system", "content": full_prompt},
        {"role": "user", "content": "Hello"},
    ]

    # First call: captures the full prompt
    result1 = mgr.prepare_messages(messages)
    assert "code_reviewer" in result1[0]["content"]

    # Simulate accidental mutation of messages[0] (should NOT affect output)
    messages[0]["content"] = "MUTATED PROMPT — this should be ignored"
    messages.append({"role": "assistant", "content": "Hi"})

    result2 = mgr.prepare_messages(messages)

    # Second call: must use frozen content, not the mutated version
    assert result2[0]["content"] == full_prompt
    assert "MUTATED" not in result2[0]["content"]
    assert "code_reviewer" in result2[0]["content"]


# =============================================================================
# Context length detection tests
# =============================================================================


@pytest.mark.asyncio
async def test_detect_context_length_updates_from_inspector():
    """detect_context_length should query Ollama and update actual_context_length."""
    mgr = OllamaContextManager(
        provisional_context_length=65536,
        host="http://localhost:11434",
        model="qwen3:32b",
    )
    assert mgr._actual_context_length == 65536

    mock_info = MagicMock()
    mock_info.max_context_length = 131072
    mock_info.family = "qwen2"
    mock_info.quantization = "Q4_K_M"

    with patch(
        "ayder_cli.core.ollama_context_manager.OllamaInspector"
    ) as MockInspector:
        instance = MockInspector.return_value
        instance.get_model_info = AsyncMock(return_value=mock_info)

        await mgr.detect_context_length()

    assert mgr._actual_context_length == 131072


@pytest.mark.asyncio
async def test_detect_context_length_falls_back_on_error():
    """If inspector fails, keep configured num_ctx."""
    mgr = OllamaContextManager(
        provisional_context_length=32768,
        host="http://localhost:11434",
        model="test:latest",
    )

    with patch(
        "ayder_cli.core.ollama_context_manager.OllamaInspector"
    ) as MockInspector:
        instance = MockInspector.return_value
        instance.get_model_info = AsyncMock(side_effect=ConnectionError("refused"))

        await mgr.detect_context_length()

    assert mgr._actual_context_length == 32768  # unchanged


@pytest.mark.asyncio
async def test_detect_context_length_falls_back_when_zero():
    """If model reports 0 context length, keep configured num_ctx."""
    mgr = OllamaContextManager(
        provisional_context_length=65536,
        host="http://localhost:11434",
        model="custom:latest",
    )

    mock_info = MagicMock()
    mock_info.max_context_length = 0
    mock_info.family = "unknown"
    mock_info.quantization = ""

    with patch(
        "ayder_cli.core.ollama_context_manager.OllamaInspector"
    ) as MockInspector:
        instance = MockInspector.return_value
        instance.get_model_info = AsyncMock(return_value=mock_info)

        await mgr.detect_context_length()

    assert mgr._actual_context_length == 65536  # unchanged


@pytest.mark.asyncio
async def test_detect_context_length_only_runs_once():
    """Second call to detect_context_length should be a no-op."""
    mgr = OllamaContextManager(
        provisional_context_length=65536,
        host="http://localhost:11434",
        model="test:latest",
    )

    mock_info = MagicMock()
    mock_info.max_context_length = 8192
    mock_info.family = "llama"
    mock_info.quantization = "Q8_0"

    with patch(
        "ayder_cli.core.ollama_context_manager.OllamaInspector"
    ) as MockInspector:
        instance = MockInspector.return_value
        instance.get_model_info = AsyncMock(return_value=mock_info)

        await mgr.detect_context_length()
        assert mgr._actual_context_length == 8192

        # Change mock to return different value
        mock_info.max_context_length = 999999
        await mgr.detect_context_length()

        # Should still be 8192 — second call is no-op
        assert mgr._actual_context_length == 8192
