"""Unit tests for retry config and error classifier."""
import httpx
import pytest

from ayder_cli.providers.retry import (
    RetryConfig,
    RetryVerdict,
    classify_error,
    compute_delay,
)


def test_retry_config_defaults():
    cfg = RetryConfig()
    assert cfg.enabled is True
    assert cfg.max_attempts == 3
    assert cfg.initial_delay_seconds == 0.5
    assert cfg.max_delay_seconds == 30.0
    assert cfg.backoff_coefficient == 2.0
    assert cfg.jitter is True


def test_retry_config_rejects_non_positive_attempts():
    with pytest.raises(ValueError):
        RetryConfig(max_attempts=0)


def test_classify_httpx_connect_error_is_retryable():
    err = httpx.ConnectError("connection refused")
    assert classify_error(err) == RetryVerdict.RETRYABLE


def test_classify_httpx_read_timeout_is_retryable():
    err = httpx.ReadTimeout("read timed out")
    assert classify_error(err) == RetryVerdict.RETRYABLE


def test_classify_value_error_is_fatal():
    assert classify_error(ValueError("bad input")) == RetryVerdict.FATAL


def test_classify_by_name_openai_rate_limit():
    class FakeRateLimitError(Exception):
        pass
    FakeRateLimitError.__module__ = "openai"
    FakeRateLimitError.__name__ = "RateLimitError"
    err = FakeRateLimitError("429")
    assert classify_error(err) == RetryVerdict.RETRYABLE


def test_classify_by_name_anthropic_connection_error():
    class FakeAPIConnectionError(Exception):
        pass
    FakeAPIConnectionError.__module__ = "anthropic"
    FakeAPIConnectionError.__name__ = "APIConnectionError"
    err = FakeAPIConnectionError("conn")
    assert classify_error(err) == RetryVerdict.RETRYABLE


def test_classify_ollama_response_error_is_retryable():
    """Bare 'EOF (status code: -1)' and similar transient ollama failures
    must be retryable so the retry layer can recover when uncommitted."""
    from ollama import ResponseError
    err = ResponseError("EOF (status code: -1)")
    assert classify_error(err) == RetryVerdict.RETRYABLE


def test_compute_delay_without_jitter_is_deterministic():
    cfg = RetryConfig(
        initial_delay_seconds=1.0,
        backoff_coefficient=2.0,
        max_delay_seconds=30.0,
        jitter=False,
    )
    assert compute_delay(cfg, attempt=0) == 1.0
    assert compute_delay(cfg, attempt=1) == 2.0
    assert compute_delay(cfg, attempt=2) == 4.0


def test_compute_delay_clamps_to_max_delay():
    cfg = RetryConfig(
        initial_delay_seconds=1.0,
        backoff_coefficient=10.0,
        max_delay_seconds=5.0,
        jitter=False,
    )
    assert compute_delay(cfg, attempt=5) == 5.0


def test_compute_delay_with_jitter_stays_in_range():
    import random
    random.seed(42)
    cfg = RetryConfig(
        initial_delay_seconds=1.0,
        backoff_coefficient=2.0,
        max_delay_seconds=30.0,
        jitter=True,
    )
    # Equal jitter: result in [base/2, base]
    for attempt in range(5):
        base = min(cfg.max_delay_seconds,
                   cfg.initial_delay_seconds * (cfg.backoff_coefficient ** attempt))
        d = compute_delay(cfg, attempt=attempt)
        assert base / 2 <= d <= base
