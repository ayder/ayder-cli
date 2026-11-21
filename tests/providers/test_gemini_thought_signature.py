"""Gemini ``thought_signature`` survives history, session files and replay (#13).

Kind: baseline regression. google-genai 3.3.0 puts the signature (``bytes``) on the
``Part`` that carries a function call. ayder dropped it, and Gemini 3 thinking models
reject replayed history without it. Keeping the raw bytes would break the JSON dumps
of session files and token estimates, so it is stored as base64 text, which the SDK
validates back to the identical bytes.

The SDK objects are real ``google.genai.types`` objects, and the end-to-end test runs
the real request path over an httpx2 ``MockTransport``; no request leaves the process
(environment: local-faked).
"""

from __future__ import annotations

import asyncio
import base64
import json
from typing import Any

import httpx2
from google import genai
from google.genai import types

from ayder_cli.core.config import Config
from ayder_cli.core.session import load_session, save_session
from ayder_cli.providers.base import ToolCallDef
from ayder_cli.providers.impl.gemini import GeminiProvider
from tests.loops.test_chat_loop_guards import _loop
from tests.providers.test_gemini_function_calls import (
    _call,
    _normalize,
    _provider,
    _response,
    _stream,
    _text,
)

SIG = bytes(range(256)) + b"\x00\xff"  # not valid UTF-8, on purpose
SIG_TEXT = base64.b64encode(SIG).decode("ascii")


def _signed_call(name: str = "read_file", args: dict | None = None) -> types.Part:
    return types.Part(
        function_call=types.FunctionCall(name=name, args=args or {"file_path": "a.py"}),
        thought_signature=SIG,
    )


# --- normalization --------------------------------------------------------------


def test_non_streaming_call_carries_the_signature_as_base64_text():
    """New interface: ToolCallDef has no thought_signature today."""
    result = _normalize(_response(_signed_call()))

    assert [tc.thought_signature for tc in result.tool_calls] == [SIG_TEXT]


def test_streaming_call_carries_the_signature_as_base64_text():
    """New interface: ToolCallDef has no thought_signature today."""
    chunks = _stream(_provider(_response(_signed_call())))

    calls = [tc for c in chunks for tc in c.tool_calls]
    assert [tc.thought_signature for tc in calls] == [SIG_TEXT]


def test_a_call_without_a_signature_has_none():
    """Preservation: other models send no signature."""
    result = _normalize(_response(_call("read_file", {"file_path": "a.py"})))
    chunks = _stream(_provider(_response(_call("read_file", {"file_path": "a.py"}))))

    assert [tc.thought_signature for tc in result.tool_calls] == [None]
    assert [tc.thought_signature for c in chunks for tc in c.tool_calls] == [None]


def test_the_signature_stays_with_its_own_call_in_a_multi_call_chunk():
    """Parallel calls: only the first Part carries a signature."""
    chunks = _stream(
        _provider(_response(_signed_call("a"), _call("b", {"x": 1}), _text("t")))
    )

    calls = [tc for c in chunks for tc in c.tool_calls]
    assert [(tc.name, tc.thought_signature) for tc in calls] == [("a", SIG_TEXT), ("b", None)]


# --- replay ---------------------------------------------------------------------


def _assistant(tool_call: dict) -> list[dict]:
    return [
        {"role": "user", "content": "go"},
        {"role": "assistant", "content": "", "tool_calls": [tool_call]},
    ]


def _function_call_part(messages: list[dict]) -> dict:
    _, converted = GeminiProvider._convert_messages(messages)
    (part,) = [p for m in converted for p in m["parts"] if "function_call" in p]
    return part


def test_replayed_function_call_part_carries_the_signature_bytes():
    """Baseline regression: the replayed part has no signature today."""
    part = _function_call_part(
        _assistant(
            {
                "id": "c1",
                "type": "function",
                "function": {"name": "read_file", "arguments": '{"file_path": "a.py"}'},
                "thought_signature": SIG_TEXT,
            }
        )
    )

    assert part["thought_signature"] == SIG_TEXT
    assert types.Part.model_validate(part).thought_signature == SIG


def test_replayed_function_call_part_without_a_signature_has_no_key():
    """Preservation: history from other providers converts as before."""
    part = _function_call_part(
        _assistant(
            {
                "id": "c1",
                "type": "function",
                "function": {"name": "read_file", "arguments": "{}"},
            }
        )
    )

    assert "thought_signature" not in part


def test_history_with_a_signature_is_json_serialisable():
    """Baseline regression: raw bytes would raise TypeError in json.dumps."""
    result = _normalize(_response(_signed_call()))
    (tc,) = result.tool_calls
    assert isinstance(tc.thought_signature, str)
    history = _assistant(
        {
            "id": tc.id,
            "type": "function",
            "function": {"name": tc.name, "arguments": tc.arguments},
            "thought_signature": tc.thought_signature,
        }
    )

    assert json.loads(json.dumps(history)) == history


# --- end to end over the real SDK request path -----------------------------------


def _sse(payload: dict[str, Any]) -> httpx2.Response:
    return httpx2.Response(
        200,
        content=("data: " + json.dumps(payload) + "\r\n\r\n").encode(),
        headers={"content-type": "text/event-stream"},
    )


def test_signature_round_trips_through_the_loop_a_saved_session_and_the_wire(tmp_path):
    """Baseline regression: the second request carries no thoughtSignature today.

    Real GeminiProvider and ChatLoop. Turn one streams a function call with a
    signature; the loop runs the tool and sends turn two, whose replayed part must
    carry the identical bytes. The saved and reloaded history (--resume) must still
    convert to a Part with those bytes.
    """
    requests: list[dict[str, Any]] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(json.loads(request.content))
        if len(requests) == 1:
            return _sse(
                {
                    "candidates": [
                        {
                            "content": {
                                "role": "model",
                                "parts": [
                                    {
                                        "functionCall": {
                                            "name": "read_file",
                                            "args": {"file_path": "a.py"},
                                        },
                                        "thoughtSignature": SIG_TEXT,
                                    }
                                ],
                            }
                        }
                    ]
                }
            )
        return _sse(
            {"candidates": [{"content": {"role": "model", "parts": [{"text": "done"}]}}]}
        )

    provider = GeminiProvider(Config(driver="google", api_key="x", model="gemini-3-test"))
    provider.client = genai.Client(
        api_key="x",
        http_options=types.HttpOptions(
            base_url="http://mock.local",
            httpx_async_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)),
        ),
    )
    loop = _loop(provider)

    asyncio.run(asyncio.wait_for(loop.run(), timeout=10))

    assert len(requests) == 2
    replayed = [
        p for c in requests[1]["contents"] for p in c["parts"] if "functionCall" in p
    ]
    assert len(replayed) == 1
    assert base64.urlsafe_b64decode(replayed[0]["thoughtSignature"]) == SIG

    sid = save_session(
        loop.messages, root=tmp_path, session_id="sig", model="gemini-3-test", provider="google"
    )
    resumed = load_session(sid, root=tmp_path).messages
    assert types.Part.model_validate(_function_call_part(resumed)).thought_signature == SIG


def test_toolcalldef_default_is_no_signature():
    """Preservation: every other driver builds ToolCallDef without it."""
    assert ToolCallDef(id="1", name="n", arguments="{}").thought_signature is None
