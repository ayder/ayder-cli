"""C3: GLM provider must not block the event loop with sync ZhipuAI client calls."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


def _make_provider():
    from ayder_cli.providers.impl.glm import GLMNativeProvider

    config = MagicMock()
    config.api_key = "test-key"
    p = GLMNativeProvider.__new__(GLMNativeProvider)
    p.config = config
    p.client = MagicMock()
    return p


def test_glm_chat_uses_asyncio_to_thread():
    """C3: chat() must wrap client.chat.completions.create in asyncio.to_thread."""
    provider = _make_provider()

    mock_response = MagicMock()

    async def _run():
        with (
            patch(
                "ayder_cli.providers.impl.glm.asyncio.to_thread",
                new=AsyncMock(return_value=mock_response),
            ) as mock_to_thread,
            patch(
                "ayder_cli.providers.impl.glm.GLMNativeProvider._normalize_response",
                return_value=MagicMock(),
            ),
        ):
            await provider.chat(
                messages=[{"role": "user", "content": "hi"}],
                model="glm-4",
            )
            return mock_to_thread.call_count

    call_count = asyncio.run(_run())
    assert call_count == 1, "asyncio.to_thread was not called — GLM blocks the event loop"


def test_glm_stream_with_tools_uses_asyncio_to_thread():
    """C3: stream_with_tools() must wrap blocking stream iteration in asyncio.to_thread."""
    provider = _make_provider()

    mock_chunk = MagicMock()

    async def _run():
        with (
            patch(
                "ayder_cli.providers.impl.glm.asyncio.to_thread",
                new=AsyncMock(return_value=[mock_chunk]),
            ) as mock_to_thread,
            patch(
                "ayder_cli.providers.impl.glm.GLMNativeProvider._normalize_chunk",
                return_value=MagicMock(),
            ),
        ):
            async for _ in provider.stream_with_tools(
                messages=[{"role": "user", "content": "hi"}],
                model="glm-4",
            ):
                pass
            return mock_to_thread.call_count

    call_count = asyncio.run(_run())
    assert call_count == 1, "asyncio.to_thread was not called in GLM stream_with_tools"
