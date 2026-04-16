"""Regression: tool results must be truncated before appending to message history.

Opus47 finding #1: full untruncated tool output was landing in self.messages,
violating the Ollama immutability contract and defeating KV-cache reuse.
"""
import pytest
from unittest.mock import MagicMock

from ayder_cli.core.context_manager import truncate_tool_result
from ayder_cli.loops.chat_loop import ChatLoop, ChatLoopConfig


class _Chunk:
    """Minimal stream chunk that ChatLoop understands."""

    def __init__(self, content="", reasoning="", tool_calls=None, usage=None):
        self.content = content
        self.reasoning = reasoning
        self.tool_calls = tool_calls or []
        self.usage = usage


class _ToolCallChunk:
    """Shape expected by ChatLoop inner loop (matches providers.base ToolCallDef)."""

    def __init__(self, call_id, name, arguments):
        self.id = call_id
        self.name = name
        self.arguments = arguments
        self._stream_index = 0


class FakeProvider:
    """Yields one tool call, then (on next turn) a plain text response."""

    def __init__(self, huge_result):
        self._turn = 0
        self._huge = huge_result

    async def stream_with_tools(self, messages, model, tools, options, verbose):
        if self._turn == 0:
            self._turn += 1
            yield _Chunk(
                tool_calls=[_ToolCallChunk("call_1", "read_file", '{"file_path": "big.txt"}')],
                usage={"total_tokens": 10, "prompt_tokens": 5, "completion_tokens": 5},
            )
        else:
            yield _Chunk(
                content="Done.",
                usage={"total_tokens": 20, "prompt_tokens": 15, "completion_tokens": 5},
            )


class FakeCallbacks:
    def __init__(self):
        self._calls = 0

    def on_thinking_start(self): pass
    def on_thinking_stop(self): pass
    def on_assistant_content(self, text): pass
    def on_thinking_content(self, text): pass
    def on_token_usage(self, total_tokens): pass
    def on_tool_start(self, call_id, name, arguments): pass
    def on_tool_complete(self, call_id, result): pass
    def on_tools_cleanup(self): pass
    def on_system_message(self, text): pass

    async def request_confirmation(self, name, arguments):
        approval = MagicMock()
        approval.action = "approve"
        return approval

    def is_cancelled(self):
        self._calls += 1
        return self._calls > 4


@pytest.mark.anyio
async def test_tool_result_truncated_in_message_history():
    """Full untruncated tool output must NOT end up in self.messages."""
    huge = "x" * 50_000  # far exceeds truncate_tool_result default of 8192 chars

    registry = MagicMock()
    registry.get_schemas.return_value = [
        {"type": "function", "function": {"name": "read_file", "parameters": {}}}
    ]
    registry.execute.return_value = huge

    config = ChatLoopConfig(permissions={"r", "w", "x"})
    messages = [{"role": "system", "content": "test"}]

    loop = ChatLoop(
        llm=FakeProvider(huge_result=huge),
        registry=registry,
        messages=messages,
        config=config,
        callbacks=FakeCallbacks(),
    )

    await loop.run()

    tool_msgs = [m for m in messages if m.get("role") == "tool"]
    assert tool_msgs, "expected at least one tool message in history"

    stored = tool_msgs[0]["content"]
    expected_truncated = truncate_tool_result(huge)

    assert stored == expected_truncated, (
        f"Tool result stored in history must equal truncate_tool_result(result). "
        f"Stored length={len(stored)}, expected length={len(expected_truncated)}, "
        f"raw length={len(huge)}."
    )
    assert len(stored) < len(huge), "Stored content must be strictly shorter than raw result"
