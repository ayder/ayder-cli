"""Gemini function calls: dict args, every part, and one id per call.

google-genai 1.73.1 returns ``FunctionCall.args`` as a plain ``dict``, so the
old ``type(args).to_dict(args)`` raised ``AttributeError`` and broke Gemini tool
use on both the streaming and non-streaming paths. The normalizers also read
only ``parts[0]`` while streaming and used the tool name as the call id, which
merged two calls to the same tool.

Responses are real ``google.genai.types`` objects; no request leaves the
process (environment: local-faked).
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from google.genai import types

from ayder_cli.providers.impl.gemini import GeminiProvider


def _response(*parts: types.Part) -> types.GenerateContentResponse:
    return types.GenerateContentResponse(
        candidates=[
            types.Candidate(content=types.Content(role="model", parts=list(parts)))
        ]
    )


def _call(name: str, args: dict, call_id: str | None = None) -> types.Part:
    return types.Part(function_call=types.FunctionCall(name=name, args=args, id=call_id))


def _text(text: str) -> types.Part:
    return types.Part(text=text)


def _provider(*stream_responses: types.GenerateContentResponse) -> GeminiProvider:
    provider = GeminiProvider.__new__(GeminiProvider)
    provider.config = SimpleNamespace(max_output_tokens=1024)
    provider.interaction_sink = None

    async def generate_content_stream(**kwargs):
        async def gen():
            for r in stream_responses:
                yield r

        return gen()

    provider.client = SimpleNamespace(
        aio=SimpleNamespace(
            models=SimpleNamespace(generate_content_stream=generate_content_stream)
        )
    )
    return provider


def _stream(provider: GeminiProvider):
    async def collect():
        out = []
        async for chunk in provider.stream_with_tools(
            [{"role": "user", "content": "hi"}], "gemini-test", tools=[]
        ):
            out.append(chunk)
        return out

    return asyncio.run(collect())


def _calls(chunks):
    return [tc for c in chunks for tc in c.tool_calls]


def _normalize(response: types.GenerateContentResponse):
    return GeminiProvider.__new__(GeminiProvider)._normalize_response(response)


# --- dict args ------------------------------------------------------------------


def test_streaming_function_call_with_dict_args():
    """Baseline regression: AttributeError on dict args today."""
    chunks = _stream(_provider(_response(_call("read_file", {"file_path": "a.py"}))))
    calls = _calls(chunks)
    assert len(calls) == 1
    assert calls[0].name == "read_file"
    assert json.loads(calls[0].arguments) == {"file_path": "a.py"}


def test_non_streaming_function_call_with_dict_args():
    """Baseline regression: AttributeError on dict args today."""
    result = _normalize(_response(_call("read_file", {"file_path": "a.py"})))
    assert [json.loads(tc.arguments) for tc in result.tool_calls] == [
        {"file_path": "a.py"}
    ]


# --- every part -------------------------------------------------------------------


def test_function_call_after_text_part_is_kept_streaming():
    """Baseline regression: only parts[0] is read while streaming today."""
    chunks = _stream(
        _provider(_response(_text("Reading it. "), _call("read_file", {"file_path": "a"})))
    )
    assert "".join(c.content for c in chunks) == "Reading it. "
    assert [tc.name for tc in _calls(chunks)] == ["read_file"]


def test_function_call_after_text_part_is_kept_non_streaming():
    """Baseline regression (dict args) with text concatenation preserved."""
    result = _normalize(
        _response(_text("A "), _text("B "), _call("read_file", {"file_path": "a"}))
    )
    assert result.content == "A B "
    assert [tc.name for tc in result.tool_calls] == ["read_file"]


def test_two_calls_in_one_chunk_streaming():
    """Baseline regression: the second call in a chunk is dropped today."""
    chunks = _stream(
        _provider(
            _response(
                _call("read_file", {"file_path": "a"}),
                _call("search_codebase", {"pattern": "x"}),
            )
        )
    )
    assert [tc.name for tc in _calls(chunks)] == ["read_file", "search_codebase"]


# --- ids --------------------------------------------------------------------------


def test_two_calls_to_same_tool_get_distinct_ids():
    """Baseline regression: both ids are the tool name today, so the chat
    loop's id match would merge the two calls into one."""
    chunks = _stream(
        _provider(
            _response(_call("read_file", {"file_path": "a"})),
            _response(_call("read_file", {"file_path": "b"})),
        )
    )
    ids = [tc.id for tc in _calls(chunks)]
    assert len(ids) == 2 and ids[0] != ids[1]
    assert all(i for i in ids)

    result = _normalize(
        _response(
            _call("read_file", {"file_path": "a"}), _call("read_file", {"file_path": "b"})
        )
    )
    ids = [tc.id for tc in result.tool_calls]
    assert len(ids) == 2 and ids[0] != ids[1]


def test_sdk_supplied_call_id_is_used():
    """Baseline regression: the SDK's own call id is ignored today."""
    chunks = _stream(_provider(_response(_call("read_file", {"file_path": "a"}, "fc-1"))))
    assert [tc.id for tc in _calls(chunks)] == ["fc-1"]

    result = _normalize(_response(_call("read_file", {"file_path": "a"}, "fc-2")))
    assert [tc.id for tc in result.tool_calls] == ["fc-2"]


# --- preservation -----------------------------------------------------------------


def test_text_only_response_unchanged():
    """Preservation: text-only responses normalize exactly as before."""
    chunks = _stream(_provider(_response(_text("Hello")), _response(_text(" world"))))
    assert "".join(c.content for c in chunks) == "Hello world"
    assert _calls(chunks) == []

    result = _normalize(_response(_text("Hello")))
    assert result.content == "Hello"
    assert result.tool_calls == []
