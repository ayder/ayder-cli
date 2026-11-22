"""Integration: runtime_factory wraps the provider in RetryingProvider when
retry.enabled is true, and wires CacheMonitor.reset() for OllamaContextManager."""

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from ayder_cli.application.runtime_factory import create_runtime
from ayder_cli.core.config import Config, RetryConfigSection
from ayder_cli.providers.retry import RetryConfig, RetryingProvider


def _minimal_config(retry_enabled: bool, driver: str = "openai") -> Config:
    return Config(
        provider="openai",
        driver=driver,
        base_url="http://localhost:11434/v1",
        api_key="test",
        model="m",
        num_ctx=8192,
        retry=RetryConfigSection(enabled=retry_enabled),
    )


def test_runtime_factory_wraps_provider_when_retry_enabled(tmp_path):
    cfg = _minimal_config(retry_enabled=True, driver="openai")
    rt = create_runtime(config=cfg, project_root=str(tmp_path))
    assert isinstance(rt.llm_provider, RetryingProvider)


def test_runtime_factory_leaves_provider_unwrapped_when_retry_disabled(tmp_path):
    cfg = _minimal_config(retry_enabled=False, driver="openai")
    rt = create_runtime(config=cfg, project_root=str(tmp_path))
    assert not isinstance(rt.llm_provider, RetryingProvider)


def test_runtime_factory_wires_cache_monitor_reset_for_ollama(tmp_path):
    """For driver='ollama', the retry hook must reset the CacheMonitor."""
    cfg = _minimal_config(retry_enabled=True, driver="ollama")
    rt = create_runtime(config=cfg, project_root=str(tmp_path))

    assert isinstance(rt.llm_provider, RetryingProvider)
    # Call the hook and assert CacheMonitor state was cleared.
    cm = rt.context_manager
    # Seed some state on the monitor so we can detect reset().
    cm._cache_monitor.record(prompt_eval_count=100, prompt_eval_ns=500_000)
    assert cm._cache_monitor._baseline_ns_per_token is not None

    rt.llm_provider._on_reconnect()  # type: ignore[attr-defined]

    assert cm._cache_monitor._baseline_ns_per_token is None
    assert cm._cache_monitor.last_status is None


def test_runtime_factory_no_cache_monitor_wiring_for_non_ollama(tmp_path):
    """For non-Ollama drivers, on_reconnect may be None (no CacheMonitor)."""
    cfg = _minimal_config(retry_enabled=True, driver="openai")
    rt = create_runtime(config=cfg, project_root=str(tmp_path))

    assert isinstance(rt.llm_provider, RetryingProvider)
    hook = rt.llm_provider._on_reconnect  # type: ignore[attr-defined]
    if hook is not None:
        hook()  # must not raise


# --- the native Qwen driver through the real retry wrapper (R13) --------------------------------------
#
# The driver is real; only dashscope's ``Generation.call`` (third-party) is faked, so every status
# the driver sees goes through its own code and the retry layer's own classification.

_REASON = "InvalidParameter: model qwen-nope is not available"


def _qwen_status(status: int, message: str = _REASON):
    return SimpleNamespace(status_code=status, message=message)


def _retrying_qwen(sleeps: list[float]):
    from ayder_cli.providers.impl.qwen import QwenNativeProvider

    driver = QwenNativeProvider.__new__(QwenNativeProvider)
    driver.config = None
    driver.api_key = "test"  # a literal placeholder; no call leaves the process

    async def record_sleep(delay: float) -> None:
        sleeps.append(delay)

    config = RetryConfig(
        max_attempts=3, initial_delay_seconds=1.0, max_delay_seconds=30.0,
        backoff_coefficient=2.0, jitter=False,
    )
    return RetryingProvider(driver, config, sleep=record_sleep)


def _stream_error_for(status: int):
    """Stream one request that answers ``status`` on every attempt.

    Returns what left the stream (an exception, or None), the attempts made and the sleeps.
    """
    dashscope = pytest.importorskip("dashscope")
    from ayder_cli.providers.impl.qwen import QwenStreamError  # noqa: F401  (import errors show here)

    sleeps: list[float] = []
    provider = _retrying_qwen(sleeps)

    async def drain():
        try:
            async for _ in provider.stream_with_tools([{"role": "user", "content": "hi"}], "qwen-turbo"):
                pass
        except Exception as exc:  # noqa: BLE001 - the test reports whatever left the stream
            return exc
        return None

    with patch.object(
        dashscope.Generation, "call", side_effect=lambda **kwargs: [_qwen_status(status)]
    ) as call:
        escaped = asyncio.run(drain())
    return escaped, call.call_count, sleeps


def test_a_404_before_any_output_raises_with_the_status_and_the_reason():
    """Baseline regression, R13: a 404 is retried as an empty response and the stream ends quietly.

    After: ``QwenStreamError`` leaves the stream, carrying the status and the upstream text.
    """
    from ayder_cli.providers.impl.qwen import QwenStreamError

    escaped, _, _ = _stream_error_for(404)

    assert isinstance(escaped, QwenStreamError)
    assert (escaped.status_code, escaped.body) == (404, _REASON)


def test_a_404_before_any_output_is_not_retried():
    """Baseline regression, R13: today the same request is made again and again, as an empty response.

    After: it fails at once, after one attempt and no wait.
    """
    _, attempts, sleeps = _stream_error_for(404)

    assert (attempts, sleeps) == (1, [])


@pytest.mark.parametrize("status", [429, 503])
def test_a_429_or_a_503_before_any_output_is_retried_with_the_same_attempts_and_delays(status):
    """Preservation: today they are retried as empty responses; after, because the classifier
    rates them retryable. The attempts (3) and delays (1 s, then 2 s) are the same either way."""
    _, attempts, sleeps = _stream_error_for(status)

    assert (attempts, sleeps) == (3, [1.0, 2.0])
