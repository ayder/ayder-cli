"""Check reasoning options on actual SDK-serialized HTTP requests."""

import json
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from ollama import AsyncClient, ResponseError
from openai import AsyncOpenAI

from ayder_cli.core.config import Config
from ayder_cli.core.reasoning import OPENAI_EFFORTS
from ayder_cli.providers.impl.openai import OpenAIProvider
from ayder_cli.providers.impl.ollama import OllamaProvider
from ayder_cli.providers.impl.ollama_drivers.generic_xml import GenericXMLDriver


@pytest.mark.asyncio
@pytest.mark.parametrize("effort", [None, *OPENAI_EFFORTS])
@pytest.mark.parametrize("stream", [False, True])
async def test_openai_wire_effort(effort, stream):
    captured = []

    def respond(request):
        captured.append(json.loads(request.content))
        response = {
            "id": "test",
            "object": "chat.completion",
            "created": 0,
            "model": "test",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "ok"},
                    "finish_reason": "stop",
                }
            ],
        }
        if stream:
            response["object"] = "chat.completion.chunk"
            response["choices"][0]["delta"] = response["choices"][0].pop("message")
            return httpx.Response(
                200,
                text="data: " + json.dumps(response) + "\n\ndata: [DONE]\n\n",
                headers={"content-type": "text/event-stream"},
            )
        return httpx.Response(200, json=response)

    provider = OpenAIProvider.__new__(OpenAIProvider)
    provider.config = Config(reasoning_effort=effort)
    provider.interaction_sink = None
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        provider.client = AsyncOpenAI(api_key="test", http_client=http)
        messages = [{"role": "user", "content": "hi"}]
        if stream:
            chunks = [c async for c in provider.stream_with_tools(messages, "test")]
            assert chunks[0].content == "ok"
        else:
            assert (await provider.chat(messages, "test")).content == "ok"
    assert len(captured) == 1
    if effort is None:
        assert "reasoning_effort" not in captured[0]
    else:
        assert captured[0]["reasoning_effort"] == effort
    assert "think" not in captured[0]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "effort,think,expected",
    [
        ("low", True, "low"),
        ("medium", False, "medium"),
        ("high", True, "high"),
        ("none", True, False),
        (None, False, False),
        (None, True, True),
        (None, "high", "high"),
        (None, None, None),
    ],
)
@pytest.mark.parametrize("xml", [False, True])
async def test_ollama_wire_effort(effort, think, expected, xml):
    captured = []

    def respond(request):
        captured.append(json.loads(request.content))
        return httpx.Response(
            200,
            text=json.dumps(
                {
                    "model": "test",
                    "message": {"role": "assistant", "content": "ok"},
                    "done": True,
                }
            )
            + "\n",
        )

    provider = OllamaProvider.__new__(OllamaProvider)
    provider.config = Config(driver="ollama", reasoning_effort=effort, think=think)
    provider._client = AsyncClient(
        host="http://test", transport=httpx.MockTransport(respond)
    )
    try:
        args = ([{"role": "user", "content": "hi"}], "test", None, None)
        iterator = (
            provider._stream_in_content(GenericXMLDriver(), *args)
            if xml
            else provider._stream_native(*args)
        )
        chunks = [c async for c in iterator]
        assert chunks[0].content == "ok"
    finally:
        await provider._client._client.aclose()
    if expected is None:
        assert "think" not in captured[0]
    else:
        assert captured[0]["think"] == expected
    assert "reasoning_effort" not in captured[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("xml", [False, True])
async def test_explicit_ollama_effort_not_silently_disabled(xml):
    provider = OllamaProvider.__new__(OllamaProvider)
    provider.config = Config(driver="ollama", reasoning_effort="high")
    provider._client = MagicMock(
        chat=AsyncMock(side_effect=ResponseError("thinking unsupported", 400))
    )
    args = ([], "test", None, None)
    iterator = (
        provider._stream_in_content(GenericXMLDriver(), *args)
        if xml
        else provider._stream_native(*args)
    )
    with pytest.raises(ResponseError):
        _ = [c async for c in iterator]
    assert provider._client.chat.await_count == 1
