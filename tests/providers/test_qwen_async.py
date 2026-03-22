"""C2: Qwen provider must not block the event loop with sync Generation.call()."""

import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock, patch


def _make_provider():
    # Mock dashscope before importing to avoid ModuleNotFoundError
    fake_dashscope = MagicMock()
    sys.modules.setdefault("dashscope", fake_dashscope)

    from ayder_cli.providers.impl.qwen import QwenNativeProvider

    config = MagicMock()
    config.api_key = "test-key"
    p = QwenNativeProvider.__new__(QwenNativeProvider)
    p.config = config
    p.api_key = "test-key"
    return p


def test_qwen_chat_uses_asyncio_to_thread():
    """C2: chat() must wrap Generation.call in asyncio.to_thread, not call it directly."""
    provider = _make_provider()

    mock_response = MagicMock()
    mock_response.status_code = 200

    async def _run():
        with (
            patch(
                "ayder_cli.providers.impl.qwen.asyncio.to_thread",
                new=AsyncMock(return_value=mock_response),
            ) as mock_to_thread,
            patch(
                "ayder_cli.providers.impl.qwen.QwenNativeProvider._normalize_response",
                return_value=MagicMock(),
            ),
        ):
            await provider.chat(
                messages=[{"role": "user", "content": "hi"}],
                model="qwen-turbo",
            )
            return mock_to_thread.call_count

    call_count = asyncio.run(_run())
    assert call_count == 1, "asyncio.to_thread was not called — Generation.call blocks the event loop"


def test_qwen_stream_with_tools_uses_asyncio_to_thread():
    """C2: stream_with_tools() must wrap Generation.call in asyncio.to_thread."""
    provider = _make_provider()

    mock_chunk = MagicMock()
    mock_chunk.status_code = 200

    async def _run():
        with (
            patch(
                "ayder_cli.providers.impl.qwen.asyncio.to_thread",
                new=AsyncMock(return_value=[mock_chunk]),
            ) as mock_to_thread,
            patch(
                "ayder_cli.providers.impl.qwen.QwenNativeProvider._normalize_chunk",
                return_value=MagicMock(),
            ),
        ):
            async for _ in provider.stream_with_tools(
                messages=[{"role": "user", "content": "hi"}],
                model="qwen-turbo",
            ):
                pass
            return mock_to_thread.call_count

    call_count = asyncio.run(_run())
    assert call_count == 1, "asyncio.to_thread was not called in stream_with_tools"
