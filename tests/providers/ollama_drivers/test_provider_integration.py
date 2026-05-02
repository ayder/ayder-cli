"""Integration tests for OllamaProvider driver routing."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ayder_cli.providers.impl.ollama import OllamaProvider


def _config(model: str, chat_protocol: str = "ollama"):
    cfg = MagicMock()
    cfg.base_url = "http://localhost:11434"
    cfg.api_key = ""
    cfg.model = model
    cfg.chat_protocol = chat_protocol
    return cfg


def _mock_chunk(content="", thinking="", done=False, tool_calls=None):
    message = MagicMock()
    message.content = content
    message.thinking = thinking
    message.tool_calls = tool_calls or []

    response = MagicMock()
    response.message = message
    response.done = done
    response.prompt_eval_count = 5 if done else None
    response.prompt_eval_duration = 100 if done else None
    response.eval_count = 3 if done else None
    response.eval_duration = 50 if done else None
    response.load_duration = 0 if done else None
    return response


@pytest.mark.asyncio
async def test_provider_routes_through_drivers():
    cfg = _config("llama3.1:8b")
    captured_kwargs: dict = {}

    async def fake_stream():
        yield _mock_chunk(content="ok", done=True)

    async def fake_chat(*args, **kwargs):
        captured_kwargs.update(kwargs)
        return fake_stream()

    fake_show = MagicMock(
        modelinfo={"llama.context_length": 32768},
        capabilities=["tools"],
        details=MagicMock(family="llama", quantization_level="Q4_K_M"),
    )

    with (
        patch("ayder_cli.providers.impl.ollama.AsyncClient") as mock_client,
        patch("ayder_cli.providers.impl.ollama_inspector.AsyncClient") as mock_inspector,
    ):
        instance = AsyncMock()
        instance.chat.side_effect = fake_chat
        instance.show = AsyncMock(return_value=fake_show)
        mock_client.return_value = instance
        mock_inspector.return_value = instance

        provider = OllamaProvider(cfg)
        async for _ in provider.stream_with_tools(
            messages=[{"role": "user", "content": "hi"}],
            model="llama3.1:8b",
            tools=[{"type": "function", "function": {"name": "read_file"}}],
        ):
            pass

    assert captured_kwargs.get("tools") is not None
    instance.show.assert_awaited_once_with("llama3.1:8b")


@pytest.mark.asyncio
async def test_chat_protocol_xml_forces_generic_xml_driver():
    cfg = _config("llama3.1:8b", chat_protocol="xml")
    captured_kwargs: dict = {}

    async def fake_stream():
        yield _mock_chunk(content="ok", done=True)

    async def fake_chat(*args, **kwargs):
        captured_kwargs.update(kwargs)
        return fake_stream()

    with (
        patch("ayder_cli.providers.impl.ollama.AsyncClient") as mock_client,
        patch("ayder_cli.providers.impl.ollama_inspector.AsyncClient") as mock_inspector,
    ):
        instance = AsyncMock()
        instance.chat.side_effect = fake_chat
        instance.show = AsyncMock()
        mock_client.return_value = instance
        mock_inspector.return_value = instance

        provider = OllamaProvider(cfg)
        async for _ in provider.stream_with_tools(
            messages=[{"role": "system", "content": "base"}],
            model="llama3.1:8b",
            tools=[{"type": "function", "function": {"name": "read_file"}}],
        ):
            pass

    assert captured_kwargs.get("tools") is None
    system_message = next(
        message for message in captured_kwargs["messages"] if message["role"] == "system"
    )
    assert "TOOL PROTOCOL:" in system_message["content"]
    instance.show.assert_not_awaited()


@pytest.mark.asyncio
async def test_driver_resolution_is_cached_across_turns():
    cfg = _config("llama3.1:8b")

    async def fake_stream():
        yield _mock_chunk(content="ok", done=True)

    fake_show = MagicMock(
        modelinfo={"llama.context_length": 32768},
        capabilities=["tools"],
        details=MagicMock(family="llama", quantization_level="Q4_K_M"),
    )

    with (
        patch("ayder_cli.providers.impl.ollama.AsyncClient") as mock_client,
        patch("ayder_cli.providers.impl.ollama_inspector.AsyncClient") as mock_inspector,
    ):
        instance = AsyncMock()
        instance.chat.side_effect = lambda *args, **kwargs: fake_stream()
        instance.show = AsyncMock(return_value=fake_show)
        mock_client.return_value = instance
        mock_inspector.return_value = instance

        provider = OllamaProvider(cfg)
        for _ in range(2):
            async for _ in provider.stream_with_tools(
                messages=[{"role": "user", "content": "hi"}],
                model="llama3.1:8b",
                tools=[{"type": "function", "function": {"name": "read_file"}}],
            ):
                pass

    instance.show.assert_awaited_once_with("llama3.1:8b")
