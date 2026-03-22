"""C1: Ollama XML protocol path builds ToolCallDef from parser output format."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

from ayder_cli.providers.base import NormalizedStreamChunk
from ayder_cli.providers.impl.ollama import OllamaProvider


def _make_provider():
    config = MagicMock()
    config.chat_protocol = "xml"
    config.base_url = "http://localhost:11434/v1"
    config.api_key = "test"
    return OllamaProvider(config)


def test_xml_protocol_correctly_maps_parser_output_to_tool_call_def():
    """C1: parser returns {name, arguments} — code must NOT use tc['function']['name']."""
    xml_content = (
        "<tool_call><function=read_file>"
        "<parameter=file_path>foo.py</parameter>"
        "</function></tool_call>"
    )
    parent_response = NormalizedStreamChunk(content=xml_content)

    provider = _make_provider()

    async def _run():
        with patch.object(
            OllamaProvider.__bases__[0],
            "chat",
            new=AsyncMock(return_value=parent_response),
        ):
            return await provider.chat(
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
    parent_response = NormalizedStreamChunk(content=xml_content)

    provider = _make_provider()

    async def _run():
        with patch.object(
            OllamaProvider.__bases__[0],
            "chat",
            new=AsyncMock(return_value=parent_response),
        ):
            return await provider.chat(
                messages=[{"role": "user", "content": "run ls"}],
                model="test-model",
                tools=[],
            )

    result = asyncio.run(_run())

    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].id  # must not be empty / None
