"""Integration: runtime_factory wraps the provider in RetryingProvider when
retry.enabled is true, and wires CacheMonitor.reset() for OllamaContextManager."""
import pytest

from ayder_cli.application.runtime_factory import create_runtime
from ayder_cli.core.config import Config, RetryConfigSection
from ayder_cli.providers.retry import RetryingProvider


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
