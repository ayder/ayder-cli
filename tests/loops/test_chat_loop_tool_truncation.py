"""Tool result truncation: generic tools are bounded by the chat-loop, while
tools that paginate their own output (``max_result_chars=0``) pass through
unmodified.

Opus47 finding #1 (the original regression this file guards): full
untruncated tool output was landing in ``self.messages``, defeating
KV-cache reuse and violating the Ollama immutability contract. That guard
is preserved here for non-exempt tools.
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


def _make_provider(tool_name: str, arguments: str = '{}'):
    class _FakeProvider:
        def __init__(self):
            self._turn = 0

        async def stream_with_tools(self, messages, model, tools, options, verbose):
            if self._turn == 0:
                self._turn += 1
                yield _Chunk(
                    tool_calls=[_ToolCallChunk("call_1", tool_name, arguments)],
                    usage={"total_tokens": 10, "prompt_tokens": 5, "completion_tokens": 5},
                )
            else:
                yield _Chunk(
                    content="Done.",
                    usage={"total_tokens": 20, "prompt_tokens": 15, "completion_tokens": 5},
                )

    return _FakeProvider()


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


def _run_loop(tool_name: str, fake_result: str, arguments: str = '{}') -> tuple[list[dict], ChatLoop]:
    registry = MagicMock()
    registry.get_schemas.return_value = [
        {"type": "function", "function": {"name": tool_name, "parameters": {}}}
    ]
    registry.execute.return_value = fake_result

    messages = [{"role": "system", "content": "test"}]
    loop = ChatLoop(
        llm=_make_provider(tool_name, arguments=arguments),
        registry=registry,
        messages=messages,
        config=ChatLoopConfig(permissions={"r", "w", "x"}),
        callbacks=FakeCallbacks(),
    )
    return messages, loop


@pytest.mark.anyio
async def test_generic_tool_result_truncated_in_message_history():
    """Tools without ``max_result_chars`` go through the loop's default
    truncation. Guards against Opus47 finding #1."""
    huge = "x" * 50_000  # far exceeds truncate_tool_result default of 8192 chars

    messages, loop = _run_loop(
        "run_shell_command", huge, arguments='{"command": "echo hi"}'
    )
    await loop.run()

    tool_msgs = [m for m in messages if m.get("role") == "tool"]
    assert tool_msgs, "expected at least one tool message in history"

    stored = tool_msgs[0]["content"]
    expected_truncated = truncate_tool_result(huge)

    assert stored == expected_truncated, (
        f"Stored length={len(stored)}, expected length={len(expected_truncated)}, "
        f"raw length={len(huge)}."
    )
    assert len(stored) < len(huge)


@pytest.mark.anyio
async def test_read_file_result_passes_through_untruncated():
    """``read_file`` declares ``max_result_chars=0`` because it paginates
    internally. The chat loop must not apply head+tail truncation to its
    output — that would silently corrupt the deliberately-bounded page."""
    paginated = "x" * 50_000  # stand-in for a fully-paginated read_file payload

    messages, loop = _run_loop(
        "read_file", paginated, arguments='{"file_path": "big.txt"}'
    )
    await loop.run()

    tool_msgs = [m for m in messages if m.get("role") == "tool"]
    assert tool_msgs, "expected at least one tool message in history"

    stored = tool_msgs[0]["content"]
    assert stored == paginated, (
        "read_file output must reach message history unmodified — "
        f"got {len(stored)} chars, expected {len(paginated)}."
    )
