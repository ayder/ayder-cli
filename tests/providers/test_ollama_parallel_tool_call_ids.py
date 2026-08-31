"""Parallel tool calls streamed one-per-chunk must get distinct ids.

Ollama's native stream sends each parallel tool call complete in its own
chunk (probed live against glm-5.3:cloud: chunks 59/60/61 carried read_file,
bash and task). The provider enumerated ids per chunk, so every chunk's first
call was "call_0". The chat loop has no _stream_index on this path and falls
back to matching by id, so the three collided into one entry: their arguments
were concatenated and the 2nd and 3rd names were discarded. The concatenated-
argument splitter then stamped the surviving name onto all three, producing
read_file calls carrying bash and task payloads.
"""

import asyncio
from types import SimpleNamespace

import pytest

from ayder_cli.providers.impl.ollama import OllamaProvider


def _tc(name, arguments):
    return SimpleNamespace(function=SimpleNamespace(name=name, arguments=arguments))


def _chunk(tool_calls=None, content="", done=False):
    return SimpleNamespace(
        message=SimpleNamespace(content=content, thinking="", tool_calls=tool_calls),
        done=done,
        prompt_eval_count=0, eval_count=0, prompt_eval_duration=0,
        eval_duration=0, load_duration=0,
    )


class _FakeClient:
    """Replays the shape the live probe observed: one complete call per chunk."""

    def __init__(self, chunks):
        self._chunks = chunks

    async def chat(self, **kwargs):
        chunks = self._chunks

        async def gen():
            for c in chunks:
                yield c

        return gen()


def _provider(chunks):
    provider = OllamaProvider.__new__(OllamaProvider)
    provider._client = _FakeClient(chunks)
    return provider


async def _collect(provider):
    seen = []
    async for chunk in provider._stream_native_once([], "m", None, None, False):
        for tc in chunk.tool_calls or []:
            seen.append((tc.id, tc.name, tc.arguments))
    return seen


def test_parallel_calls_streamed_one_per_chunk_get_distinct_ids():
    chunks = [
        _chunk([_tc("read_file", '{"file_path": "/etc/hostname"}')]),
        _chunk([_tc("bash", '{"command": "echo hello"}')]),
        _chunk([_tc("task", '{"action": "create"}')], done=True),
    ]
    seen = asyncio.run(_collect(_provider(chunks)))

    assert [s[1] for s in seen] == ["read_file", "bash", "task"]
    ids = [s[0] for s in seen]
    assert len(set(ids)) == 3, f"ids collided: {ids}"


def test_multiple_calls_inside_one_chunk_also_get_distinct_ids():
    chunks = [
        _chunk([_tc("read_file", "{}"), _tc("bash", "{}")]),
        _chunk([_tc("task", "{}")], done=True),
    ]
    seen = asyncio.run(_collect(_provider(chunks)))

    ids = [s[0] for s in seen]
    assert len(set(ids)) == 3, f"ids collided: {ids}"


def test_ids_are_stable_within_a_single_call():
    """A lone tool call keeps a simple id — no behaviour change for the common case."""
    chunks = [_chunk([_tc("read_file", '{"file_path": "x"}')], done=True)]
    seen = asyncio.run(_collect(_provider(chunks)))
    assert len(seen) == 1
