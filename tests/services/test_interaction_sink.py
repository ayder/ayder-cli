"""Tests for InteractionSink protocol and TUIInteractionSink."""

from typing import Any
from unittest.mock import Mock

import pytest


class TestInteractionSinkProtocol:
    def test_protocol_is_runtime_checkable(self):
        from ayder_cli.services.interactions import InteractionSink
        assert hasattr(InteractionSink, "_is_runtime_protocol")

    def test_protocol_has_on_llm_request_debug(self):
        from ayder_cli.services.interactions import InteractionSink
        assert "on_llm_request_debug" in dir(InteractionSink)

    def test_mock_satisfies_protocol(self):
        from ayder_cli.services.interactions import InteractionSink
        mock = Mock(spec=InteractionSink)
        assert isinstance(mock, InteractionSink)


class TestTUIInteractionSink:
    def test_on_llm_request_debug_calls_callback(self):
        from ayder_cli.tui.adapter import TUIInteractionSink
        cb = Mock()
        sink = TUIInteractionSink(on_llm_request_debug_cb=cb)
        messages = [{"role": "user", "content": "hi"}]
        sink.on_llm_request_debug(messages, "gpt-4", None, None)
        cb.assert_called_once_with(messages, "gpt-4", None, None)

    def test_on_llm_request_debug_noop_without_callback(self):
        from ayder_cli.tui.adapter import TUIInteractionSink
        sink = TUIInteractionSink()
        # Should not raise
        sink.on_llm_request_debug([], "gpt-4", None, None)

    def test_satisfies_interaction_sink_protocol(self):
        from ayder_cli.services.interactions import InteractionSink
        from ayder_cli.tui.adapter import TUIInteractionSink
        assert isinstance(TUIInteractionSink(), InteractionSink)


class TestProviderAcceptsSink:
    def test_openai_provider_accepts_and_calls_sink(self):
        from ayder_cli.providers.impl.openai import OpenAIProvider
        from ayder_cli.services.interactions import InteractionSink

        sink = Mock(spec=InteractionSink)
        config = Mock()
        config.base_url = "http://mock"
        config.api_key = "mock"

        provider = OpenAIProvider(config=config, interaction_sink=sink)
        assert provider.interaction_sink is sink

    def test_verbose_mode_triggers_on_llm_request_debug(self):
        import asyncio
        from unittest.mock import AsyncMock
        from ayder_cli.providers.impl.openai import OpenAIProvider
        from ayder_cli.services.interactions import InteractionSink

        sink = Mock(spec=InteractionSink)
        mock_client = Mock()
        choice = Mock()
        choice.message.content = "response"
        choice.message.reasoning_content = ""
        choice.message.tool_calls = []
        mock_response = Mock()
        mock_response.choices = [choice]
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        config = Mock()
        config.base_url = "http://mock"
        config.api_key = "mock"

        provider = OpenAIProvider(config=config, interaction_sink=sink)
        provider.client = mock_client

        asyncio.run(provider.chat([{"role": "user", "content": "hi"}], "gpt-4", verbose=True))
        sink.on_llm_request_debug.assert_called_once()
