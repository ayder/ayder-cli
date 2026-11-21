"""Each driver's tool-call shape reaches the loop as the right calls (plan step 13, D5).

The call assembler (``_ToolCallAssembler``) takes over the loop's delta handling. These rows pin
what every driver's adapter feeds the real ``ChatLoop`` and what history and results come out, so
that the extraction and the identity rules (R9a, R9e) cannot change a shape a driver depends on:

- OpenAI: index deltas, with two interleaved calls (``_stream_index`` on every delta);
- DeepSeek: the name arrives in a later delta than the id;
- Claude: argument deltas carry the ``tool_use`` block's id;
- Gemini: the thought signature travels with its call;
- Ollama: complete calls, one per chunk;
- complete calls in content: the XML driver's parsed calls.

Kind: preservation (every row passes before and after). Environment: local-faked. Layer: unit.
No request leaves the process: the OpenAI and DeepSeek rows build their SDK stream with
``httpx2.MockTransport`` passed to the SDK client, and the others use the fake SDK stream their
provider's own tests use.
"""

from __future__ import annotations

import base64
import json
from types import SimpleNamespace

import httpx2
from google.genai import types
from openai import AsyncOpenAI

from ayder_cli.core.config import Config
from ayder_cli.core.result import ToolSuccess
from ayder_cli.providers.base import NormalizedStreamChunk
from ayder_cli.providers.impl.claude import ClaudeProvider
from ayder_cli.providers.impl.deepseek import DeepSeekProvider
from ayder_cli.providers.impl.gemini import GeminiProvider
from ayder_cli.providers.impl.ollama import OllamaProvider
from ayder_cli.providers.impl.ollama_drivers.generic_xml import GenericXMLDriver
from ayder_cli.providers.impl.openai import OpenAIProvider
from tests.loops.turn_fakes import (
    RecordingRegistry,
    assistant_calls,
    make_loop,
    run_turn,
    tool_messages,
)
from tests.providers.test_claude_stream_tool_calls import (
    _FakeMessages,
    _json_delta,
    _text_delta,
    _text_start,
    _tool_start,
)

_A = '{"file_path": "a.py"}'
_DIR = '{"path": "."}'
_RESULT_A = "read_file:[('file_path', 'a.py')]"
_RESULT_DIR = "file_explorer:[('path', '.')]"


class _EchoRegistry(RecordingRegistry):
    """Each tool answers with its own name and arguments, so a result says whose it is."""

    def execute(self, name, arguments):
        self.calls.append((name, dict(arguments)))
        return ToolSuccess(f"{name}:{sorted(arguments.items())}")


def _history_of(provider):
    """Run one turn over ``provider`` and return the calls and results history ended with."""
    loop = make_loop(provider, registry=_EchoRegistry())
    run_turn(loop)
    calls = {
        c["id"]: (c["function"]["name"], c["function"]["arguments"]) for c in assistant_calls(loop)
    }
    results = {m["tool_call_id"]: m["content"] for m in tool_messages(loop)}
    return loop, calls, results


class _SecondRequestIsText:
    """Presents one adapter stream as a provider; the loop's second request is answered in text."""

    def __init__(self, first_stream):
        self._first_stream = first_stream
        self.requests = 0

    async def stream_with_tools(self, messages, model, tools=None, options=None, verbose=False):
        self.requests += 1
        if self.requests == 1:
            async for chunk in self._first_stream(messages, model, tools, options):
                yield chunk
        else:
            yield NormalizedStreamChunk(content="done")


# -- OpenAI and DeepSeek: SSE through httpx2.MockTransport ---------------------------------------------


def _sse(*deltas: dict, finish: str | None = None) -> bytes:
    lines = []
    for i, delta in enumerate(deltas):
        last = i == len(deltas) - 1 and finish
        payload = {
            "id": "chatcmpl-1",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "m",
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish if last else None}],
        }
        lines.append(f"data: {json.dumps(payload)}\n\n")
    lines.append("data: [DONE]\n\n")
    return "".join(lines).encode()


def _call_delta(index: int, *, id: str | None = None, name: str | None = None, arguments: str = ""):
    function: dict = {"arguments": arguments}
    if name is not None:
        function["name"] = name
    call: dict = {"index": index, "function": function}
    if id is not None:
        call.update(id=id, type="function")
    return {"tool_calls": [call]}


def _openai_client(first_reply: bytes) -> AsyncOpenAI:
    """An SDK client whose first request streams ``first_reply`` and whose next ones say "done"."""
    requests = {"n": 0}

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests["n"] += 1
        body = first_reply if requests["n"] == 1 else _sse({"content": "done"}, finish="stop")
        return httpx2.Response(200, headers={"content-type": "text/event-stream"}, content=body)

    return AsyncOpenAI(
        base_url="http://mock/v1",
        api_key="x",
        max_retries=0,
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)),
    )


def _config() -> Config:
    return Config(
        provider="openai",
        driver="openai",
        base_url="http://localhost:11434/v1",
        api_key="test",
        model="m",
        num_ctx=8192,
    )


def test_openai_index_deltas_with_two_interleaved_calls():
    """OpenAI: every delta carries its call's index, so two interleaved calls stay apart."""
    provider = OpenAIProvider(_config())
    provider.client = _openai_client(
        _sse(
            _call_delta(0, id="call_a", name="read_file", arguments='{"file_path": '),
            _call_delta(1, id="call_b", name="file_explorer", arguments='{"path": '),
            _call_delta(0, arguments='"a.py"}'),
            _call_delta(1, arguments='"."}'),
            {},
            finish="tool_calls",
        )
    )

    _, calls, results = _history_of(provider)

    assert calls == {"call_a": ("read_file", _A), "call_b": ("file_explorer", _DIR)}
    assert results == {"call_a": _RESULT_A, "call_b": _RESULT_DIR}


def test_deepseek_name_arriving_after_the_id():
    """DeepSeek: the id and part of the arguments come first, the name in a later delta."""
    provider = DeepSeekProvider(_config())
    provider.base_provider.client = _openai_client(
        _sse(
            _call_delta(0, id="call_a", arguments='{"file_path": '),
            _call_delta(0, name="read_file", arguments='"a.py"}'),
            {},
            finish="tool_calls",
        )
    )

    _, calls, results = _history_of(provider)

    assert calls == {"call_a": ("read_file", _A)}
    assert results == {"call_a": _RESULT_A}


# -- Claude -----------------------------------------------------------------------------------------------------


def test_claude_argument_deltas_keyed_by_their_tool_use_block():
    """Claude: ``input_json_delta`` events carry only the block index; the provider maps each back
    to its ``tool_use`` id, so two sequential blocks become two calls."""
    provider = ClaudeProvider.__new__(ClaudeProvider)
    provider.config = SimpleNamespace(max_output_tokens=1024)
    provider.interaction_sink = None
    provider.client = SimpleNamespace(
        messages=_FakeMessages(
            [
                [
                    _tool_start(0, "toolu_A", "read_file"),
                    _json_delta(0, '{"file_path": '),
                    _json_delta(0, '"a.py"}'),
                    _tool_start(1, "toolu_B", "file_explorer"),
                    _json_delta(1, '{"path": '),
                    _json_delta(1, '"."}'),
                ],
                [_text_start(0), _text_delta(0, "done")],
            ]
        )
    )

    _, calls, results = _history_of(provider)

    assert calls == {"toolu_A": ("read_file", _A), "toolu_B": ("file_explorer", _DIR)}
    assert results == {"toolu_A": _RESULT_A, "toolu_B": _RESULT_DIR}


# -- Gemini -----------------------------------------------------------------------------------------------------

_SIGNATURE = bytes(range(256)) + b"\x00\xff"


def test_gemini_thought_signature_travels_with_its_call():
    """Gemini: the signature the provider puts on the call is kept on the stored call."""

    def response(*parts: types.Part) -> types.GenerateContentResponse:
        return types.GenerateContentResponse(
            candidates=[types.Candidate(content=types.Content(role="model", parts=list(parts)))]
        )

    scripts = [
        [
            response(
                types.Part(
                    function_call=types.FunctionCall(
                        name="read_file", args={"file_path": "a.py"}, id="g1"
                    ),
                    thought_signature=_SIGNATURE,
                )
            )
        ],
        [response(types.Part(text="done"))],
    ]
    provider = GeminiProvider.__new__(GeminiProvider)
    provider.config = SimpleNamespace(max_output_tokens=1024)
    provider.interaction_sink = None

    async def generate_content_stream(**kwargs):
        async def gen():
            for item in scripts.pop(0):
                yield item

        return gen()

    provider.client = SimpleNamespace(
        aio=SimpleNamespace(models=SimpleNamespace(generate_content_stream=generate_content_stream))
    )

    loop, calls, results = _history_of(provider)

    assert calls == {"g1": ("read_file", _A)}
    assert results == {"g1": _RESULT_A}
    (stored,) = assistant_calls(loop)
    assert stored["thought_signature"] == base64.b64encode(_SIGNATURE).decode("ascii")


# -- Ollama: complete calls, one per chunk ------------------------------------------------------------------------


def _ollama_chunk(content: str = "", tool_calls=None, done: bool = False):
    return SimpleNamespace(
        message=SimpleNamespace(content=content, thinking="", tool_calls=tool_calls),
        done=done,
        prompt_eval_count=0, eval_count=0, prompt_eval_duration=0,
        eval_duration=0, load_duration=0,
    )


def _ollama_call(name: str, arguments: str):
    return SimpleNamespace(function=SimpleNamespace(name=name, arguments=arguments))


class _OllamaClient:
    def __init__(self, chunks):
        self._chunks = chunks

    async def chat(self, **kwargs):
        chunks = self._chunks

        async def gen():
            for c in chunks:
                yield c

        return gen()


def test_ollama_complete_calls_one_per_chunk():
    """Ollama: each call arrives complete, with ids the driver numbers across the whole stream."""
    provider = OllamaProvider.__new__(OllamaProvider)
    provider._client = _OllamaClient(
        [
            _ollama_chunk(tool_calls=[_ollama_call("read_file", _A)]),
            _ollama_chunk(tool_calls=[_ollama_call("file_explorer", _DIR)], done=True),
        ]
    )

    async def first(messages, model, tools, options):
        async for chunk in provider._stream_native_once(messages, model, tools, options, False):
            yield chunk

    _, calls, results = _history_of(_SecondRequestIsText(first))

    assert calls == {"call_0": ("read_file", _A), "call_1": ("file_explorer", _DIR)}
    assert results == {"call_0": _RESULT_A, "call_1": _RESULT_DIR}


# -- Complete calls in content ---------------------------------------------------------------------------------------


def test_complete_calls_parsed_out_of_content():
    """In-content protocols: the driver's parser returns complete calls with its own ids."""
    provider = OllamaProvider.__new__(OllamaProvider)
    content = (
        "<tool_call><function=read_file><parameter=file_path>a.py</parameter></function></tool_call>"
        "<tool_call><function=file_explorer><parameter=path>.</parameter></function></tool_call>"
    )
    provider._client = _OllamaClient([_ollama_chunk(content=content, done=True)])

    async def first(messages, model, tools, options):
        async for chunk in provider._stream_in_content_once(
            GenericXMLDriver(), messages, model, tools, options, False
        ):
            yield chunk

    _, calls, results = _history_of(_SecondRequestIsText(first))

    assert list(calls) == ["call_0", "call_1"]
    assert [calls[i][0] for i in calls] == ["read_file", "file_explorer"]
    assert [json.loads(calls[i][1]) for i in calls] == [{"file_path": "a.py"}, {"path": "."}]
    assert results == {"call_0": _RESULT_A, "call_1": _RESULT_DIR}
