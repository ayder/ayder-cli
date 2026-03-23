"""C1: Ollama XML protocol path builds ToolCallDef from parser output format."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

from ayder_cli.providers.base import NormalizedStreamChunk
from ayder_cli.providers.impl.ollama import OllamaProvider


def _make_provider():
    config = MagicMock()
    config.chat_protocol = "xml"
    config.base_url = "http://localhost:11434"
    config.api_key = "test"
    return OllamaProvider(config)


def _make_stream_chunk(content="", thinking="", done=False):
    """Create a mock ollama stream chunk."""
    msg = MagicMock()
    msg.content = content
    msg.thinking = thinking
    msg.tool_calls = []

    resp = MagicMock()
    resp.message = msg
    resp.done = done
    resp.prompt_eval_count = 5 if done else None
    resp.prompt_eval_duration = 100 if done else None
    resp.eval_count = 3 if done else None
    resp.eval_duration = 50 if done else None
    resp.load_duration = 0 if done else None
    return resp


def test_xml_protocol_correctly_maps_parser_output_to_tool_call_def():
    """C1: parser returns {name, arguments} — code must NOT use tc['function']['name']."""
    xml_content = (
        "<tool_call><function=read_file>"
        "<parameter=file_path>foo.py</parameter>"
        "</function></tool_call>"
    )

    provider = _make_provider()

    async def _run():
        async def mock_stream(*args, **kwargs):
            yield _make_stream_chunk(content=xml_content, done=True)

        with patch("ayder_cli.providers.impl.ollama.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.chat.return_value = mock_stream()
            MockClient.return_value = instance

            # Re-create provider inside patch context so _client uses the mock
            cfg = MagicMock()
            cfg.chat_protocol = "xml"
            cfg.base_url = "http://localhost:11434"
            cfg.api_key = "test"
            p = OllamaProvider(cfg)

            return await p.chat(
                messages=[{"role": "user", "content": "read foo.py"}],
                model="test-model",
                tools=[{"type": "function", "function": {"name": "read_file"}}],
            )

    result = asyncio.run(_run())

    assert len(result.tool_calls) == 1
    tc = result.tool_calls[0]
    assert tc.name == "read_file"
    assert json.loads(tc.arguments) == {"file_path": "foo.py"}


def test_xml_protocol_assigns_fallback_id_when_parser_omits_it():
    """C1: parser never returns 'id', so a generated id must be used (not KeyError)."""
    xml_content = (
        "<tool_call><function=run_tool>"
        "<parameter=cmd>ls</parameter>"
        "</function></tool_call>"
    )

    async def _run():
        async def mock_stream(*args, **kwargs):
            yield _make_stream_chunk(content=xml_content, done=True)

        with patch("ayder_cli.providers.impl.ollama.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.chat.return_value = mock_stream()
            MockClient.return_value = instance

            cfg = MagicMock()
            cfg.chat_protocol = "xml"
            cfg.base_url = "http://localhost:11434"
            cfg.api_key = "test"
            p = OllamaProvider(cfg)

            return await p.chat(
                messages=[{"role": "user", "content": "run ls"}],
                model="test-model",
                tools=[],
            )

    result = asyncio.run(_run())

    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].id  # must not be empty / None
