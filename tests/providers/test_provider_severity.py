"""Severity is asserted on the production call path, not on simulated traffic."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

# scripts/ is on sys.path via tests/conftest.py (§C15).
from logging_gates import BATCHES, collect, resolve  # noqa: E402

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


class _FakeDriver:
    name = "generic_xml"
    mode = SimpleNamespace(value="xml")


async def test_driver_selection_is_info_on_the_production_path(loguru_caplog):
    """`Ollama driver=...` is a lifecycle transition -> INFO (not DEBUG)."""
    from ayder_cli.providers.impl.ollama import OllamaProvider

    cfg = SimpleNamespace(base_url="http://localhost:11434", chat_protocol="ollama",
                          model="test-model", num_ctx=4096)
    provider = OllamaProvider(cfg)
    provider._registry = SimpleNamespace(resolve=AsyncMock(return_value=_FakeDriver()))

    async def _no_chunks(*a, **k):
        return
        yield                                    # pragma: no cover

    with patch.object(provider, "_stream_with_driver", _no_chunks):
        async for _ in provider.stream_with_tools(
            [{"role": "user", "content": "hi"}], "test-model", None
        ):
            pass

    hits = [r for r in loguru_caplog.records if r["message"].startswith("Ollama driver=")]
    assert hits, "driver-selection record never emitted"
    assert hits[0]["level"].name == "INFO"
    assert hits[0]["extra"]["channel"] == "llm"


async def test_stream_kwargs_is_trace_on_the_production_path(loguru_caplog):
    """`Stream kwargs:` carries the full payload -> TRACE (not DEBUG)."""
    from ayder_cli.providers.impl.openai import OpenAIProvider

    cfg = SimpleNamespace(base_url=None, api_key="k", model="gpt-x",
                          provider="openai", num_ctx=None)
    provider = OpenAIProvider(cfg)

    provider.client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=AsyncMock(side_effect=RuntimeError("halt")))
        )
    )
    with pytest.raises(RuntimeError):
        async for _ in provider.stream_with_tools(
            [{"role": "user", "content": "hi"}], "gpt-x", None
        ):
            pass

    hits = [r for r in loguru_caplog.records if r["message"].startswith("Stream kwargs:")]
    assert hits, "stream-kwargs record never emitted"
    assert hits[0]["level"].name == "TRACE"
    assert hits[0]["extra"]["channel"] == "llm"


# --- AST assertion: supplements the production tests, never replaces them ---

EXPECTED = {
    "providers/impl/claude.py :: ClaudeProvider.stream_with_tools :: Claude Chunk: type=": "trace",
    "providers/impl/gemini.py :: GeminiProvider.stream_with_tools :: Gemini Chunk Received": "trace",
    "providers/impl/openai.py :: OpenAIProvider.stream_with_tools :: Stream kwargs:": "trace",
    "providers/impl/ollama.py :: OllamaProvider.stream_with_tools :: Ollama driver=": "info",
    "providers/impl/openai.py :: OpenAIProvider.stream_with_tools :: Stream completed:": "debug",
    "providers/impl/openai.py :: OpenAIProvider.stream_with_tools :: Stream yielded zero chunks": "warning",
    "providers/impl/qwen.py :: QwenNativeProvider.stream_with_tools :: Qwen streaming error": "error",
    "providers/retry.py :: RetryingProvider.stream_with_tools :: Empty response from provider": "info",
}


@pytest.mark.parametrize("identity,level", sorted(EXPECTED.items()))
def test_frozen_levels(identity, level):
    assert resolve(identity, collect(BATCHES["providers"]))["level"] == level
