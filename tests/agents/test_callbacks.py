"""Tests for AgentCallbacks — autonomous agent callback implementation."""

import asyncio
import pytest
from ayder_cli.agents.callbacks import AgentCallbacks
from ayder_cli.loops.chat_loop import ChatCallbacks


class TestAgentCallbacks:
    def test_implements_protocol(self):
        """AgentCallbacks must satisfy the ChatCallbacks protocol."""
        cancel_event = asyncio.Event()
        cb = AgentCallbacks(agent_name="test", cancel_event=cancel_event)
        assert isinstance(cb, ChatCallbacks)

    def test_on_assistant_content(self):
        cancel_event = asyncio.Event()
        cb = AgentCallbacks(agent_name="test", cancel_event=cancel_event)
        # Should not raise — just collects content
        cb.on_assistant_content("Hello world")
        assert cb.last_content == "Hello world"

    def test_on_assistant_content_accumulates(self):
        cancel_event = asyncio.Event()
        cb = AgentCallbacks(agent_name="test", cancel_event=cancel_event)
        cb.on_assistant_content("Hello ")
        cb.on_assistant_content("world")
        assert cb.last_content == "Hello world"

    def test_is_cancelled_false_by_default(self):
        cancel_event = asyncio.Event()
        cb = AgentCallbacks(agent_name="test", cancel_event=cancel_event)
        assert cb.is_cancelled() is False

    def test_is_cancelled_true_when_event_set(self):
        cancel_event = asyncio.Event()
        cb = AgentCallbacks(agent_name="test", cancel_event=cancel_event)
        cancel_event.set()
        assert cb.is_cancelled() is True

    @pytest.mark.anyio
    async def test_request_confirmation_auto_approves(self):
        cancel_event = asyncio.Event()
        cb = AgentCallbacks(agent_name="test", cancel_event=cancel_event)
        result = await cb.request_confirmation("run_shell_command", {"command": "ls"})
        assert result is not None
        assert getattr(result, "action", None) == "approve"

    def test_noop_methods_dont_raise(self):
        """All no-op callbacks should not raise."""
        cancel_event = asyncio.Event()
        cb = AgentCallbacks(agent_name="test", cancel_event=cancel_event)
        cb.on_thinking_start()
        cb.on_thinking_stop()
        cb.on_thinking_content("thinking...")
        cb.on_token_usage(100)
        cb.on_tool_start("id1", "read_file", {"path": "test.py"})
        cb.on_tool_complete("id1", "file contents")
        cb.on_tools_cleanup()
        cb.on_system_message("System message")

    def test_on_progress_callback(self):
        """If on_progress is provided, it receives agent events."""
        events = []
        cancel_event = asyncio.Event()
        cb = AgentCallbacks(
            agent_name="test",
            cancel_event=cancel_event,
            on_progress=lambda name, event, data: events.append((name, event, data)),
        )
        cb.on_tool_start("id1", "read_file", {"path": "test.py"})
        assert len(events) == 1
        assert events[0][0] == "test"
        assert events[0][1] == "tool_start"
