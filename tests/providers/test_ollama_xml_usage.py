"""Regression: XML fallback streamer must preserve usage metadata on the
final done chunk even when content is empty.

Opus47 finding #5: usage was gated behind `if content_text or thinking_text`
so done=True chunks with no text dropped usage on the floor. This corrupted
OllamaContextManager state (stale _real_prompt_tokens → wrong compaction).
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from ayder_cli.providers.impl.ollama import OllamaProvider


def _chunk(content="", thinking="", done=False, pec=0, ped=0, ec=0, ed=0):
    msg = MagicMock()
    msg.content = content
    msg.thinking = thinking
    msg.tool_calls = []
    resp = MagicMock()
    resp.message = msg
    resp.done = done
    resp.prompt_eval_count = pec
    resp.prompt_eval_duration = ped
    resp.eval_count = ec
    resp.eval_duration = ed
    resp.load_duration = 0
    return resp


def _make_provider():
    cfg = MagicMock()
    cfg.chat_protocol = "xml"
    cfg.base_url = "http://localhost:11434"
    cfg.api_key = "test"
    return OllamaProvider(cfg)


def test_xml_fallback_emits_usage_on_empty_final_chunk():
    """When the final done chunk has no text, usage must still be yielded."""

    async def _run():
        async def mock_stream(*args, **kwargs):
            # First chunk carries XML content, no done flag
            yield _chunk(content="<tool_call><function=read_file>"
                                 "<parameter=p>x</parameter>"
                                 "</function></tool_call>")
            # Second chunk is done but empty (the bug-triggering case)
            yield _chunk(content="", done=True,
                         pec=123, ped=456_000, ec=10, ed=200_000)

        with patch("ayder_cli.providers.impl.ollama.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.chat.return_value = mock_stream()
            MockClient.return_value = instance

            provider = _make_provider()

            observed_usages = []
            async for out in provider.stream_with_tools(
                messages=[{"role": "user", "content": "go"}],
                model="test-model",
                tools=[{"type": "function", "function": {"name": "read_file"}}],
            ):
                if out.usage is not None:
                    observed_usages.append(out.usage)

            return observed_usages

    usages = asyncio.run(_run())

    assert usages, "Expected at least one chunk carrying usage data"
    last = usages[-1]
    assert last["prompt_tokens"] == 123
    assert last["prompt_eval_ns"] == 456_000
    assert last["completion_tokens"] == 10
    assert last["eval_ns"] == 200_000
