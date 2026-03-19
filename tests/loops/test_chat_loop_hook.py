"""Tests for ChatLoop pre-iteration hook."""

import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock

from ayder_cli.loops.chat_loop import ChatLoop, ChatLoopConfig


class FakeProvider:
    async def stream_with_tools(self, *a, **k):
        # Yield one text-only chunk then stop
        from ayder_cli.providers import NormalizedStreamChunk
        chunk = NormalizedStreamChunk()
        chunk.content = "Hello"
        chunk.done = True
        yield chunk


class FakeCallbacks:
    def __init__(self):
        self.cancelled = False
        self.call_count = 0

    def on_thinking_start(self): pass
    def on_thinking_stop(self): pass
    def on_assistant_content(self, text): pass
    def on_thinking_content(self, text): pass
    def on_token_usage(self, total_tokens): pass
    def on_tool_start(self, call_id, name, arguments): pass
    def on_tool_complete(self, call_id, result): pass
    def on_tools_cleanup(self): pass
    def on_system_message(self, text): pass
    async def request_confirmation(self, name, arguments): return None
    def is_cancelled(self):
        self.call_count += 1
        # Cancel after first iteration to prevent infinite loop
        if self.call_count > 1:
            return True
        return self.cancelled


class TestPreIterationHook:
    @pytest.mark.anyio
    async def test_hook_called_before_llm(self):
        """pre_iteration_hook is called at the top of each iteration."""
        hook_called = []

        async def my_hook(messages):
            hook_called.append(len(messages))

        config = ChatLoopConfig()
        config.pre_iteration_hook = my_hook

        loop = ChatLoop(
            llm=FakeProvider(),
            registry=MagicMock(get_schemas=MagicMock(return_value=[])),
            messages=[{"role": "system", "content": "test"}],
            config=config,
            callbacks=FakeCallbacks(),
        )

        await loop.run()
        assert len(hook_called) >= 1

    @pytest.mark.anyio
    async def test_no_hook_no_error(self):
        """ChatLoop works fine without a pre_iteration_hook."""
        config = ChatLoopConfig()

        loop = ChatLoop(
            llm=FakeProvider(),
            registry=MagicMock(get_schemas=MagicMock(return_value=[])),
            messages=[{"role": "system", "content": "test"}],
            config=config,
            callbacks=FakeCallbacks(),
        )

        # Should not raise
        await loop.run()
