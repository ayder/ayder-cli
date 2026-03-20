"""Tests for TuiChatLoop — the async chat loop for the Textual TUI."""

import json
from unittest.mock import MagicMock

import pytest

from ayder_cli.providers import (
    AIProvider,
    NormalizedStreamChunk,
    ToolCallDef,
    _ToolCall,
    _FunctionCall,
)
from ayder_cli.tui.chat_loop import (
    TuiChatLoop,
    TuiLoopConfig,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class FakeAIProvider(AIProvider):
    def __init__(self):
        self.stream_chunks = []
        self.call_count = 0

    async def chat(self, *a, **k):
        return NormalizedStreamChunk()

    async def stream_with_tools(self, *a, **k):
        self.call_count += 1
        for chunk in self.stream_chunks:
            yield chunk


class FakeCallbacks:
    def __init__(self):
        self.events = []
        self._cancelled = False
        self._confirm_result = None

    def on_thinking_start(self): self.events.append(("thinking_start",))
    def on_thinking_stop(self): self.events.append(("thinking_stop",))
    def on_assistant_content(self, text): self.events.append(("assistant_content", text))
    def on_thinking_content(self, text): self.events.append(("thinking_content", text))
    def on_token_usage(self, total): self.events.append(("token_usage", total))

    def on_tool_start(self, cid, name, args): self.events.append(("tool_start", cid, name, args))
    def on_tool_complete(self, cid, res): self.events.append(("tool_complete", cid, res))
    def on_tools_cleanup(self): self.events.append(("tools_cleanup",))
    def on_system_message(self, text): self.events.append(("system_message", text))
    async def request_confirmation(self, n, a): return self._confirm_result
    def is_cancelled(self): return self._cancelled


def _make_chunk(content="", reasoning="", tool_calls=None, usage=None):
    calls = []
    if tool_calls:
        for i, tc in enumerate(tool_calls):
            if hasattr(tc, "function"):
                calls.append(ToolCallDef(id=tc.id, name=tc.function.name, arguments=tc.function.arguments))
            else:
                calls.append(ToolCallDef(id=tc.get("id", f"c{i}"), name=tc["function"]["name"], arguments=tc["function"]["arguments"]))
    return NormalizedStreamChunk(content=content, reasoning=reasoning, tool_calls=calls, usage=usage)


def _make_tool_call(call_id="tc-1", name="read_file", arguments=None):
    return _ToolCall(id=call_id, function=_FunctionCall(name=name, arguments=json.dumps(arguments or {"file_path": "test.py"})))


def _make_loop(cb=None, messages=None, permissions=None):
    llm = FakeAIProvider()
    registry = MagicMock()
    registry.get_schemas.return_value = [{"type": "function", "function": {"name": "read_file"}}]
    registry.execute.return_value = "file content"
    cb = cb or FakeCallbacks()
    messages = messages if messages is not None else [{"role": "system", "content": "sys"}, {"role": "user", "content": "hello"}]
    loop = TuiChatLoop(llm, registry, messages, TuiLoopConfig(permissions=permissions or {"r"}), cb)
    return loop, cb, llm, registry


@pytest.mark.anyio
async def test_text_only_response():
    loop, cb, llm, _ = _make_loop()
    llm.stream_chunks = [_make_chunk(content="Hello!", usage={"total_tokens": 42})]
    
    await loop.run()
    assert ("assistant_content", "Hello!") in cb.events
    assert len(loop.messages) == 3


@pytest.mark.anyio
async def test_tool_execution():
    loop, cb, llm, _ = _make_loop(permissions={"r"})
    tc = _make_tool_call(call_id="c1", name="read_file")
    
    # We need a stateful generator for multiple calls
    class StatefulProvider(FakeAIProvider):
        async def stream_with_tools(self, *a, **k):
            self.call_count += 1
            if self.call_count == 1:
                yield _make_chunk(tool_calls=[tc])
            else:
                yield _make_chunk(content="Done")
    
    loop.llm = StatefulProvider()
    await loop.run()
    assert ("tool_start", "c1", "read_file", {}) in cb.events
    assert len(loop.messages) == 5



