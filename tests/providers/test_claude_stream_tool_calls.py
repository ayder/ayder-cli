"""Claude streaming: argument deltas must attach to their own tool_use block.

Anthropic streams a tool call as ``content_block_start`` (id + name) followed by
``input_json_delta`` events that carry only the block ``index``. The provider
must map that index back to the tool_use id, otherwise the chat loop cannot
match the delta to its call and builds a second, nameless call.

The SDK stream is faked with real ``anthropic.types`` event models, so no
request leaves the process (environment: local-faked).
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from anthropic.types import (
    InputJSONDelta,
    RawContentBlockDeltaEvent,
    RawContentBlockStartEvent,
    TextBlock,
    TextDelta,
    ToolUseBlock,
)

from ayder_cli.loops.chat_loop import ChatLoop, ChatLoopConfig
from ayder_cli.providers.impl.claude import ClaudeProvider


# --- fakes -------------------------------------------------------------------


class _FakeStream:
    def __init__(self, events):
        self._events = events

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        for event in self._events:
            yield event


class _FakeMessages:
    """Returns one scripted event list per ``stream()`` call."""

    def __init__(self, scripts):
        self._scripts = list(scripts)

    def stream(self, **kwargs):
        return _FakeStream(self._scripts.pop(0))


def _provider(*scripts) -> ClaudeProvider:
    provider = ClaudeProvider.__new__(ClaudeProvider)
    provider.config = SimpleNamespace(max_output_tokens=1024)
    provider.interaction_sink = None
    provider.client = SimpleNamespace(messages=_FakeMessages(scripts))
    return provider


def _text_start(index: int):
    return RawContentBlockStartEvent(
        type="content_block_start",
        index=index,
        content_block=TextBlock(type="text", text=""),
    )


def _text_delta(index: int, text: str):
    return RawContentBlockDeltaEvent(
        type="content_block_delta",
        index=index,
        delta=TextDelta(type="text_delta", text=text),
    )


def _tool_start(index: int, tool_id: str, name: str):
    return RawContentBlockStartEvent(
        type="content_block_start",
        index=index,
        content_block=ToolUseBlock(type="tool_use", id=tool_id, name=name, input={}),
    )


def _json_delta(index: int, partial: str):
    return RawContentBlockDeltaEvent(
        type="content_block_delta",
        index=index,
        delta=InputJSONDelta(type="input_json_delta", partial_json=partial),
    )


async def _collect(provider):
    chunks = []
    async for chunk in provider.stream_with_tools(
        [{"role": "user", "content": "hi"}], "claude-test", tools=[]
    ):
        chunks.append(chunk)
    return chunks


def _run(coro):
    return asyncio.run(coro)


# --- provider-level ------------------------------------------------------------


def test_stream_deltas_carry_the_tool_use_id():
    """Baseline regression: deltas are emitted with id "" today."""
    provider = _provider(
        [
            _tool_start(0, "toolu_A", "read_file"),
            _json_delta(0, '{"file_path": '),
            _json_delta(0, '"a.py"}'),
        ]
    )
    chunks = _run(_collect(provider))
    calls = [tc for c in chunks for tc in c.tool_calls]
    assert [c.id for c in calls] == ["toolu_A", "toolu_A", "toolu_A"]
    assert calls[0].name == "read_file"
    assert "".join(c.arguments for c in calls) == '{"file_path": "a.py"}'


def test_text_deltas_unchanged():
    """Preservation: text blocks still stream as content."""
    provider = _provider([_text_start(0), _text_delta(0, "Hel"), _text_delta(0, "lo")])
    chunks = _run(_collect(provider))
    assert "".join(c.content for c in chunks) == "Hello"
    assert all(not c.tool_calls for c in chunks)


# --- through the real chat loop --------------------------------------------------


class _Callbacks:
    def __init__(self):
        self.started: list[tuple[str, str]] = []

    def on_thinking_start(self): ...
    def on_thinking_stop(self): ...
    def on_assistant_content(self, text): ...
    def on_thinking_content(self, text): ...
    def on_token_usage(self, total_tokens): ...
    def on_tool_start(self, call_id, name, arguments):
        self.started.append((call_id, name))
    def on_tool_complete(self, call_id, result): ...
    def on_tools_cleanup(self): ...
    def on_system_message(self, text): ...
    async def request_confirmation(self, name, arguments):
        return SimpleNamespace(action="approve")
    def is_cancelled(self):
        return False


class _PassThroughContext:
    session_id = None
    run_id = None

    def prepare_messages(self, messages, max_history=0):
        return list(messages)

    def update_from_response(self, usage):
        pass


def _run_loop(provider):
    registry = MagicMock()
    registry.get_schemas.return_value = []
    registry.execute.return_value = "ok"
    messages = [{"role": "user", "content": "go"}]
    loop = ChatLoop(
        llm=provider,
        registry=registry,
        messages=messages,
        config=ChatLoopConfig(model="claude-test", provider="anthropic"),
        callbacks=_Callbacks(),
        context_manager=_PassThroughContext(),
    )
    _run(loop.run())
    return messages, registry


def test_chat_loop_assembles_one_named_call_from_claude_stream():
    """Baseline regression: the loop builds a second, nameless call today."""
    provider = _provider(
        [
            _tool_start(0, "toolu_A", "read_file"),
            _json_delta(0, '{"file_path": '),
            _json_delta(0, '"a.py"}'),
        ],
        [_text_start(0), _text_delta(0, "done")],
    )
    messages, registry = _run_loop(provider)

    assistant = next(m for m in messages if m.get("tool_calls"))
    calls = assistant["tool_calls"]
    assert len(calls) == 1
    assert calls[0]["id"] == "toolu_A"
    assert calls[0]["function"]["name"] == "read_file"
    assert json.loads(calls[0]["function"]["arguments"]) == {"file_path": "a.py"}
    tool_msgs = [m for m in messages if m["role"] == "tool"]
    assert [m["tool_call_id"] for m in tool_msgs] == ["toolu_A"]
    assert registry.execute.call_count == 1


def test_two_parallel_tool_uses_after_text_block_stay_separate():
    """Baseline regression: block indices count the text block, and each
    tool_use's deltas must still land on their own call."""
    provider = _provider(
        [
            _text_start(0),
            _text_delta(0, "Reading both."),
            _tool_start(1, "toolu_A", "read_file"),
            _json_delta(1, '{"file_path": "a.py"}'),
            _tool_start(2, "toolu_B", "read_file"),
            _json_delta(2, '{"file_path": '),
            _json_delta(2, '"b.py"}'),
        ],
        [_text_start(0), _text_delta(0, "done")],
    )
    messages, registry = _run_loop(provider)

    assistant = next(m for m in messages if m.get("tool_calls"))
    assert assistant["content"] == "Reading both."
    calls = assistant["tool_calls"]
    assert [c["id"] for c in calls] == ["toolu_A", "toolu_B"]
    assert [json.loads(c["function"]["arguments"]) for c in calls] == [
        {"file_path": "a.py"},
        {"file_path": "b.py"},
    ]
    assert registry.execute.call_count == 2
