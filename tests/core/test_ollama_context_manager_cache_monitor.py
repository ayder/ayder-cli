"""Regression: CacheMonitor must be instantiated and wired into OllamaContextManager.

Opus47 finding #2: _cache_monitor was declared as None, never assigned, so
the entire KV-cache-aware design (adaptive compaction, hit ratio reporting)
was dead code.
"""
from ayder_cli.core.cache_monitor import CacheMonitor
from ayder_cli.core.ollama_context_manager import OllamaContextManager


def make_manager():
    return OllamaContextManager(
        provisional_context_length=100_000,
        reserve_ratio=0.3,
        compaction_threshold=0.7,
    )


def test_cache_monitor_instantiated():
    mgr = make_manager()
    assert isinstance(mgr._cache_monitor, CacheMonitor), \
        "_cache_monitor must be a CacheMonitor instance at __init__ time"


def test_cache_hit_ratio_exposed_in_stats_after_samples():
    """After two update_from_response calls, stats.cache_hit_ratio must be non-None."""
    mgr = make_manager()
    mgr.freeze_system_prompt("S", [])

    # First response: establishes baseline
    mgr.update_from_response({
        "prompt_tokens": 1000,
        "completion_tokens": 50,
        "prompt_eval_ns": 10_000_000,  # 10k ns/tok
        "eval_ns": 500_000,
    })

    # Second response: much faster → cache hit
    mgr.update_from_response({
        "prompt_tokens": 1000,
        "completion_tokens": 50,
        "prompt_eval_ns": 1_000_000,   # 1k ns/tok → hot
        "eval_ns": 500_000,
    })

    stats = mgr.get_stats()
    assert stats.cache_hit_ratio is not None, \
        "get_stats().cache_hit_ratio must be populated after samples arrive"
    assert stats.cache_hit_ratio > 0.5, \
        f"Expected hot cache hit ratio > 0.5, got {stats.cache_hit_ratio}"


def test_adaptive_threshold_when_cache_hot():
    """When cache is hot, compaction threshold pushes to 0.90 (delay compaction)."""
    mgr = make_manager()
    mgr.freeze_system_prompt("S", [])

    # Make the cache hot
    mgr.update_from_response({
        "prompt_tokens": 1000,
        "completion_tokens": 50,
        "prompt_eval_ns": 10_000_000,
    })
    mgr.update_from_response({
        "prompt_tokens": 1000,
        "completion_tokens": 50,
        "prompt_eval_ns": 1_000_000,  # 10x faster → hot
    })

    # Simulate large prompt usage that is over 0.7 budget but under 0.9 budget.
    # budget = ceiling * (1 - 0.3) = 70_000
    # At 0.7 threshold → compact at >= 49_000
    # At 0.9 threshold → compact at >= 63_000
    # Set _real_prompt_tokens to 55_000 — above 0.7, below 0.9.
    mgr._real_prompt_tokens = 55_000

    assert mgr.should_compact() is False, \
        "With hot cache, threshold should push to 0.9 and defer compaction at 55k tokens"


def test_cold_threshold_unchanged_without_hot_signal():
    """Without a hot cache signal, the configured 0.7 threshold still applies."""
    mgr = make_manager()
    mgr.freeze_system_prompt("S", [])

    # Only one sample — cold state
    mgr.update_from_response({
        "prompt_tokens": 55_000,
        "completion_tokens": 50,
        "prompt_eval_ns": 10_000_000,
    })

    assert mgr.should_compact() is True, \
        "Cold cache state should not elevate the compaction threshold"
