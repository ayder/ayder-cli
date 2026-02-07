"""Tests for services/llm.py"""
import pytest
from unittest.mock import Mock, patch
from ayder_cli.services.llm import LLMProvider, OpenAIProvider


class TestLLMProvider:
    """Test abstract base class."""

    def test_cannot_instantiate_directly(self):
        """LLMProvider is abstract — cannot instantiate."""
        with pytest.raises(TypeError):
            LLMProvider()

    def test_subclass_must_implement_chat(self):
        """Subclass without chat() raises TypeError."""
        class BadProvider(LLMProvider):
            pass
        with pytest.raises(TypeError):
            BadProvider()


class TestOpenAIProvider:
    """Test OpenAIProvider."""

    def test_init_with_injected_client(self):
        """Constructor uses injected client when provided."""
        mock_client = Mock()
        provider = OpenAIProvider(client=mock_client)
        assert provider.client is mock_client

    @patch("ayder_cli.services.llm.OpenAI")
    def test_init_creates_client_when_not_injected(self, mock_openai_cls):
        """Constructor creates OpenAI client when no client injected."""
        provider = OpenAIProvider(base_url="http://localhost:11434/v1", api_key="key")
        mock_openai_cls.assert_called_once_with(base_url="http://localhost:11434/v1", api_key="key")
        assert provider.client is mock_openai_cls.return_value

    def test_chat_basic_call(self):
        """chat() passes model and messages to client."""
        mock_client = Mock()
        mock_client.chat.completions.create.return_value = Mock(choices=[Mock()])
        provider = OpenAIProvider(client=mock_client)

        messages = [{"role": "user", "content": "hello"}]
        provider.chat(messages, model="test-model")

        mock_client.chat.completions.create.assert_called_once()
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["model"] == "test-model"
        assert call_kwargs["messages"] == messages
        assert "tools" not in call_kwargs

    def test_chat_with_tools(self):
        """chat() includes tools and tool_choice when tools provided."""
        mock_client = Mock()
        provider = OpenAIProvider(client=mock_client)
        tools = [{"type": "function", "function": {"name": "test"}}]

        provider.chat([], model="m", tools=tools)

        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["tools"] == tools
        assert call_kwargs["tool_choice"] == "auto"

    def test_chat_with_options(self):
        """chat() passes options as extra_body."""
        mock_client = Mock()
        provider = OpenAIProvider(client=mock_client)

        provider.chat([], model="m", options={"num_ctx": 8192})

        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["extra_body"] == {"options": {"num_ctx": 8192}}

    def test_chat_without_tools_or_options(self):
        """chat() omits tools and extra_body when not provided."""
        mock_client = Mock()
        provider = OpenAIProvider(client=mock_client)

        provider.chat([{"role": "user", "content": "hi"}], model="m")

        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert "tools" not in call_kwargs
        assert "extra_body" not in call_kwargs

    def test_chat_returns_response(self):
        """chat() returns the raw response from the client."""
        mock_client = Mock()
        mock_response = Mock()
        mock_client.chat.completions.create.return_value = mock_response
        provider = OpenAIProvider(client=mock_client)

        result = provider.chat([], model="m")
        assert result is mock_response

    def test_chat_with_both_tools_and_options(self):
        """chat() includes both tools and options when provided."""
        mock_client = Mock()
        provider = OpenAIProvider(client=mock_client)
        tools = [{"type": "function", "function": {"name": "test"}}]

        provider.chat([], model="m", tools=tools, options={"temperature": 0.5})

        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["tools"] == tools
        assert call_kwargs["tool_choice"] == "auto"
        assert call_kwargs["extra_body"] == {"options": {"temperature": 0.5}}
