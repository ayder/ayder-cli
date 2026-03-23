"""Tests for CacheMonitor — timing-based KV-cache hit detection."""
import pytest
from ayder_cli.core.cache_monitor import CacheMonitor


def test_first_record_is_cold():
    mon = CacheMonitor()
    status = mon.record(prompt_eval_count=100, prompt_eval_ns=1_000_000)
    assert status.state == "cold"
    assert status.hit_ratio == 0.0


def test_cache_hit_detected():
    """Much faster than baseline → hot."""
    mon = CacheMonitor()
    mon.record(prompt_eval_count=100, prompt_eval_ns=1_000_000)  # baseline: 10000 ns/tok
    status = mon.record(prompt_eval_count=100, prompt_eval_ns=100_000)  # 10x faster
    assert status.state == "hot"
    assert status.hit_ratio > 0.5


def test_cache_warm():
    """Moderately faster → warm."""
    mon = CacheMonitor()
    mon.record(prompt_eval_count=100, prompt_eval_ns=1_000_000)  # baseline
    status = mon.record(prompt_eval_count=100, prompt_eval_ns=500_000)  # 2x faster
    assert status.state == "warm"


def test_cache_miss():
    """Same speed as baseline → miss."""
    mon = CacheMonitor()
    mon.record(prompt_eval_count=100, prompt_eval_ns=1_000_000)
    status = mon.record(prompt_eval_count=100, prompt_eval_ns=900_000)  # ~same
    assert status.state == "miss"


def test_reset_clears_baseline():
    mon = CacheMonitor()
    mon.record(prompt_eval_count=100, prompt_eval_ns=1_000_000)
    mon.reset()
    status = mon.record(prompt_eval_count=100, prompt_eval_ns=500_000)
    assert status.state == "cold"  # Treated as new baseline


def test_last_status_property():
    mon = CacheMonitor()
    assert mon.last_status is None
    mon.record(prompt_eval_count=10, prompt_eval_ns=100_000)
    assert mon.last_status is not None
    assert mon.last_status.state == "cold"


def test_zero_prompt_eval_count_no_crash():
    """Should handle edge case of 0 tokens without division by zero."""
    mon = CacheMonitor()
    status = mon.record(prompt_eval_count=0, prompt_eval_ns=0)
    assert status.state == "cold"
