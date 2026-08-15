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
    """`Stream kwargs` names the request KEYS -> TRACE (not DEBUG).

    The level pin is unchanged; the record now carries key names only, so the
    control also asserts that no kwarg VALUE reaches the message.
    """
    from ayder_cli.providers.impl.openai import OpenAIProvider

    cfg = SimpleNamespace(base_url=None, api_key="k", model="gpt-x",
                          provider="openai", num_ctx=None)
    provider = OpenAIProvider(cfg)

    provider.client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=AsyncMock(side_effect=RuntimeError("halt")))
        )
    )
    prompt_sentinel = "PROMPT-CANARY-hunter2"
    with pytest.raises(RuntimeError):
        async for _ in provider.stream_with_tools(
            [{"role": "user", "content": prompt_sentinel}], "gpt-x", None
        ):
            pass

    hits = [r for r in loguru_caplog.records if r["message"].startswith("Stream kwargs")]
    assert hits, "stream-kwargs record never emitted"
    assert hits[0]["level"].name == "TRACE"
    assert hits[0]["extra"]["channel"] == "llm"
    # Keys only: `model` is a key that is present, `gpt-x` is its value.
    keys = hits[0]["message"].split(": ", 1)[1]
    assert "model" in keys
    assert "gpt-x" not in loguru_caplog.text
    assert prompt_sentinel not in loguru_caplog.text
    assert "=" not in keys              # the old `k={v!r}` rendering is gone
    assert "messages" not in keys       # the payload key stays excluded


# --- AST assertion: supplements the production tests, never replaces them ---

EXPECTED = {
    "providers/impl/claude.py :: ClaudeProvider.stream_with_tools :: Claude Chunk: type=": "trace",
    "providers/impl/gemini.py :: GeminiProvider.stream_with_tools :: Gemini Chunk Received": "trace",
    "providers/impl/openai.py :: OpenAIProvider.stream_with_tools :: Stream kwargs": "trace",
    "providers/impl/ollama.py :: OllamaProvider.stream_with_tools :: Ollama driver=": "info",
    "providers/impl/openai.py :: OpenAIProvider.stream_with_tools :: Stream completed:": "debug",
    "providers/impl/openai.py :: OpenAIProvider.stream_with_tools :: Stream yielded zero chunks": "warning",
    "providers/impl/qwen.py :: QwenNativeProvider.stream_with_tools :: Qwen streaming error": "error",
    "providers/retry.py :: RetryingProvider.stream_with_tools :: Empty response from provider": "info",
}


@pytest.mark.parametrize("identity,level", sorted(EXPECTED.items()))
def test_frozen_levels(identity, level):
    assert resolve(identity, collect(BATCHES["providers"]))["level"] == level
