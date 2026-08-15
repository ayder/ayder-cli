"""Tests for reactive fallback on classified Ollama tool bugs."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from ollama import ResponseError

from ayder_cli.providers.impl.ollama import OllamaProvider
from ayder_cli.providers.impl.ollama_drivers._errors import OllamaServerToolBug

# Arbitrary server-side tail text appended to a classified signature: the
# fallback record must carry the exception TYPE and none of this.
SERVER_ERROR_SENTINEL = "near-token=hunter2-LEAKCANARY"


def _config():
    cfg = MagicMock()
    cfg.base_url = "http://localhost:11434"
    cfg.api_key = ""
    cfg.chat_protocol = "ollama"
    return cfg


def _mock_chunk(content="", done=False, tool_calls=None):
    message = MagicMock()
    message.content = content
    message.thinking = ""
    message.tool_calls = tool_calls or []

    response = MagicMock()
    response.message = message
    response.done = done
    response.prompt_eval_count = 0
    response.prompt_eval_duration = 0
    response.eval_count = 0
    response.eval_duration = 0
    response.load_duration = 0
    return response


def _show(family: str = "qwen3"):
    return MagicMock(
        modelinfo={f"{family}.context_length": 32768},
        capabilities=["tools"],
        details=MagicMock(family=family, quantization_level="Q4"),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error_message",
    [
        "XML syntax error on line 43: unexpected EOF",
        "failed to parse JSON: unexpected end of JSON input",
    ],
)
async def test_fallback_engages_when_uncommitted_tool_bug(error_message, loguru_caplog):
    cfg = _config()
    call_count = {"chat": 0}
    # The classified signature still matches (substring), but the raised text
    # now carries arbitrary upstream tail content that must never be logged.
    raised_message = f"{error_message} {SERVER_ERROR_SENTINEL}"

    async def fail_then_succeed(*args, **kwargs):
        call_count["chat"] += 1
        if call_count["chat"] == 1:
            async def boom():
                raise ResponseError(raised_message)
                yield

            return boom()

        async def ok():
            yield _mock_chunk(content="recovered", done=True)

        return ok()

    with (
        patch("ayder_cli.providers.impl.ollama.AsyncClient") as mock_client,
        patch("ayder_cli.providers.impl.ollama_inspector.AsyncClient") as mock_inspector,
    ):
        instance = AsyncMock()
        instance.chat.side_effect = fail_then_succeed
        instance.show = AsyncMock(return_value=_show())
        mock_client.return_value = instance
        mock_inspector.return_value = instance

        provider = OllamaProvider(cfg)
        chunks = []
        async for chunk in provider.stream_with_tools(
            messages=[{"role": "user", "content": "hi"}],
            model="qwen3.6:latest",
            tools=[{"type": "function", "function": {"name": "x"}}],
        ):
            chunks.append(chunk)

    assert call_count["chat"] == 2
    assert any("recovered" in chunk.content for chunk in chunks)

    # The fallback record names the failure TYPE, never the server's text.
    hits = [r for r in loguru_caplog.records if "failed mid-stream" in r["message"]]
    assert hits, "fallback record never emitted"
    assert "error_type=OllamaServerToolBug" in hits[0]["message"]
    assert SERVER_ERROR_SENTINEL not in loguru_caplog.text
    assert error_message not in loguru_caplog.text


@pytest.mark.asyncio
async def test_fallback_does_not_engage_after_committed_chunk():
    cfg = _config()

    async def stream_then_fail(*args, **kwargs):
        async def gen():
            yield _mock_chunk(content="committed text")
            raise ResponseError("XML syntax error: unexpected EOF")

        return gen()

    with (
        patch("ayder_cli.providers.impl.ollama.AsyncClient") as mock_client,
        patch("ayder_cli.providers.impl.ollama_inspector.AsyncClient") as mock_inspector,
    ):
        instance = AsyncMock()
        instance.chat.side_effect = stream_then_fail
        instance.show = AsyncMock(return_value=_show())
        mock_client.return_value = instance
        mock_inspector.return_value = instance

        provider = OllamaProvider(cfg)
        chunks = []
        with pytest.raises(Exception):
            async for chunk in provider.stream_with_tools(
                messages=[{"role": "user", "content": "hi"}],
                model="qwen3.6:latest",
                tools=[{"type": "function", "function": {"name": "x"}}],
            ):
                chunks.append(chunk)

    assert any("committed" in chunk.content for chunk in chunks)


@pytest.mark.asyncio
async def test_fallback_does_not_engage_on_non_tool_bug_error():
    cfg = _config()

    async def boom(*args, **kwargs):
        async def gen():
            raise ResponseError("internal server error")
            yield

        return gen()

    with (
        patch("ayder_cli.providers.impl.ollama.AsyncClient") as mock_client,
        patch("ayder_cli.providers.impl.ollama_inspector.AsyncClient") as mock_inspector,
    ):
        instance = AsyncMock()
        instance.chat.side_effect = boom
        instance.show = AsyncMock(return_value=_show())
        mock_client.return_value = instance
        mock_inspector.return_value = instance

        provider = OllamaProvider(cfg)
        with pytest.raises(ResponseError):
            async for _ in provider.stream_with_tools(
                messages=[{"role": "user", "content": "hi"}],
                model="qwen3.6:latest",
                tools=[{"type": "function", "function": {"name": "x"}}],
            ):
                pass


@pytest.mark.asyncio
async def test_leaf_generic_xml_tool_bug_propagates():
    cfg = _config()
    cfg.chat_protocol = "xml"

    async def boom(*args, **kwargs):
        async def gen():
            raise ResponseError("XML syntax error: unexpected EOF")
            yield

        return gen()

    with patch("ayder_cli.providers.impl.ollama.AsyncClient") as mock_client:
        instance = AsyncMock()
        instance.chat.side_effect = boom
        mock_client.return_value = instance

        provider = OllamaProvider(cfg)
        with pytest.raises(OllamaServerToolBug):
            async for _ in provider.stream_with_tools(
                messages=[{"role": "user", "content": "hi"}],
                model="llama3.1:8b",
                tools=[{"type": "function", "function": {"name": "x"}}],
            ):
                pass

    assert instance.chat.await_count == 1
