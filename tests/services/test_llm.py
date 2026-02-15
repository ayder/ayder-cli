"""Tests for services/llm.py"""
import json
import pytest
from unittest.mock import Mock, patch
from ayder_cli.services.llm import (
    LLMProvider,
    OpenAIProvider,
    AnthropicProvider,
    create_llm_provider,
    _Response,
    _ANTHROPIC_MODELS_FALLBACK,
)


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


class TestAnthropicProvider:
    """Test AnthropicProvider."""

    def test_init_with_injected_client(self):
        """Constructor uses injected client when provided."""
        mock_client = Mock()
        provider = AnthropicProvider(client=mock_client)
        assert provider.client is mock_client

    def test_system_message_extraction(self):
        """System messages are extracted into a separate system string."""
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello"},
        ]
        system, converted = AnthropicProvider._convert_messages(messages)
        assert system == "You are helpful."
        assert len(converted) == 1
        assert converted[0]["role"] == "user"
        assert converted[0]["content"] == "Hello"

    def test_multiple_system_messages_joined(self):
        """Multiple system messages are joined with double newlines."""
        messages = [
            {"role": "system", "content": "Part 1"},
            {"role": "system", "content": "Part 2"},
            {"role": "user", "content": "Hi"},
        ]
        system, _ = AnthropicProvider._convert_messages(messages)
        assert system == "Part 1\n\nPart 2"

    def test_tool_schema_translation(self):
        """OpenAI tool schemas are converted to Anthropic format."""
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Read a file",
                    "parameters": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                        "required": ["path"],
                    },
                },
            }
        ]
        result = AnthropicProvider._convert_tools(tools)
        assert len(result) == 1
        assert result[0]["name"] == "read_file"
        assert result[0]["description"] == "Read a file"
        assert result[0]["input_schema"]["type"] == "object"
        assert "path" in result[0]["input_schema"]["properties"]

    def test_text_only_response_wrapping(self):
        """Text-only Anthropic response is wrapped correctly."""
        mock_response = Mock()
        text_block = Mock()
        text_block.type = "text"
        text_block.text = "Hello world"
        mock_response.content = [text_block]
        mock_response.usage = Mock(input_tokens=10, output_tokens=5)

        result = AnthropicProvider._wrap_response(mock_response)

        assert isinstance(result, _Response)
        assert result.choices[0].message.content == "Hello world"
        assert result.choices[0].message.tool_calls == []
        assert result.usage.total_tokens == 15

    def test_tool_use_response_wrapping(self):
        """Tool-use Anthropic response is wrapped with tool_calls."""
        mock_response = Mock()
        tool_block = Mock()
        tool_block.type = "tool_use"
        tool_block.id = "toolu_123"
        tool_block.name = "read_file"
        tool_block.input = {"path": "/tmp/test.txt"}
        mock_response.content = [tool_block]
        mock_response.usage = Mock(input_tokens=20, output_tokens=10)

        result = AnthropicProvider._wrap_response(mock_response)

        assert result.choices[0].message.content is None
        tc = result.choices[0].message.tool_calls
        assert len(tc) == 1
        assert tc[0].id == "toolu_123"
        assert tc[0].type == "function"
        assert tc[0].function.name == "read_file"
        assert json.loads(tc[0].function.arguments) == {"path": "/tmp/test.txt"}

    def test_mixed_text_and_tool_response(self):
        """Response with both text and tool_use blocks."""
        mock_response = Mock()
        text_block = Mock()
        text_block.type = "text"
        text_block.text = "Let me read that file."
        tool_block = Mock()
        tool_block.type = "tool_use"
        tool_block.id = "toolu_456"
        tool_block.name = "write_file"
        tool_block.input = {"path": "x.py", "content": "print('hi')"}
        mock_response.content = [text_block, tool_block]
        mock_response.usage = Mock(input_tokens=30, output_tokens=20)

        result = AnthropicProvider._wrap_response(mock_response)

        assert result.choices[0].message.content == "Let me read that file."
        assert len(result.choices[0].message.tool_calls) == 1
        assert result.usage.total_tokens == 50

    def test_tool_result_message_translation(self):
        """Tool result messages (role=tool) are converted to user/tool_result blocks."""
        messages = [
            {"role": "user", "content": "Read the file"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "tc_1",
                        "type": "function",
                        "function": {"name": "read_file", "arguments": '{"path":"a.txt"}'},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "tc_1", "content": "file contents"},
        ]
        _, converted = AnthropicProvider._convert_messages(messages)

        # user, assistant (tool_use), user (tool_result)
        assert len(converted) == 3
        # Tool result should be a user message with tool_result block
        tool_result_msg = converted[2]
        assert tool_result_msg["role"] == "user"
        assert tool_result_msg["content"][0]["type"] == "tool_result"
        assert tool_result_msg["content"][0]["tool_use_id"] == "tc_1"
        assert tool_result_msg["content"][0]["content"] == "file contents"

    def test_consecutive_user_messages_merged(self):
        """Consecutive user messages are merged into one."""
        messages = [
            {"role": "user", "content": "First"},
            {"role": "user", "content": "Second"},
        ]
        _, converted = AnthropicProvider._convert_messages(messages)

        assert len(converted) == 1
        assert converted[0]["role"] == "user"
        # Merged into list of text blocks
        assert len(converted[0]["content"]) == 2
        assert converted[0]["content"][0] == {"type": "text", "text": "First"}
        assert converted[0]["content"][1] == {"type": "text", "text": "Second"}

    def test_usage_token_calculation(self):
        """Total tokens = input_tokens + output_tokens."""
        mock_response = Mock()
        mock_response.content = []
        mock_response.usage = Mock(input_tokens=100, output_tokens=50)

        result = AnthropicProvider._wrap_response(mock_response)
        assert result.usage.total_tokens == 150

    def test_list_models_calls_api(self):
        """list_models() fetches models from the Anthropic API."""
        mock_client = Mock()
        model1 = Mock()
        model1.id = "claude-opus-4-6"
        model2 = Mock()
        model2.id = "claude-sonnet-4-5-20250929"
        mock_page = Mock()
        mock_page.data = [model1, model2]
        mock_client.models.list.return_value = mock_page

        provider = AnthropicProvider(client=mock_client)
        models = provider.list_models()
        assert models == ["claude-opus-4-6", "claude-sonnet-4-5-20250929"]
        mock_client.models.list.assert_called_once_with(limit=100)

    def test_list_models_falls_back_on_api_error(self):
        """list_models() returns fallback list when the API call fails."""
        mock_client = Mock()
        mock_client.models.list.side_effect = Exception("API error")

        provider = AnthropicProvider(client=mock_client)
        models = provider.list_models()
        assert models == list(_ANTHROPIC_MODELS_FALLBACK)

    def test_list_models_falls_back_on_empty_response(self):
        """list_models() returns fallback list when the API returns no models."""
        mock_client = Mock()
        mock_page = Mock()
        mock_page.data = []
        mock_client.models.list.return_value = mock_page

        provider = AnthropicProvider(client=mock_client)
        models = provider.list_models()
        assert models == list(_ANTHROPIC_MODELS_FALLBACK)

    def test_chat_calls_client(self):
        """chat() calls the Anthropic client with translated args."""
        mock_client = Mock()
        mock_response = Mock()
        text_block = Mock()
        text_block.type = "text"
        text_block.text = "Hi"
        mock_response.content = [text_block]
        mock_response.usage = Mock(input_tokens=5, output_tokens=3)
        mock_client.messages.create.return_value = mock_response

        provider = AnthropicProvider(client=mock_client)
        result = provider.chat(
            [{"role": "user", "content": "hello"}],
            model="claude-sonnet-4-5-20250929",
        )

        mock_client.messages.create.assert_called_once()
        assert isinstance(result, _Response)
        assert result.choices[0].message.content == "Hi"

    def test_chat_passes_max_tokens_from_options(self):
        """chat() maps options.num_ctx to max_tokens."""
        mock_client = Mock()
        mock_response = Mock()
        mock_response.content = []
        mock_response.usage = Mock(input_tokens=0, output_tokens=0)
        mock_client.messages.create.return_value = mock_response

        provider = AnthropicProvider(client=mock_client)
        provider.chat(
            [{"role": "user", "content": "hi"}],
            model="m",
            options={"num_ctx": 16384},
        )

        call_kwargs = mock_client.messages.create.call_args[1]
        assert call_kwargs["max_tokens"] == 16384

    def test_chat_default_max_tokens(self):
        """chat() uses 8192 as default max_tokens."""
        mock_client = Mock()
        mock_response = Mock()
        mock_response.content = []
        mock_response.usage = Mock(input_tokens=0, output_tokens=0)
        mock_client.messages.create.return_value = mock_response

        provider = AnthropicProvider(client=mock_client)
        provider.chat(
            [{"role": "user", "content": "hi"}],
            model="m",
        )

        call_kwargs = mock_client.messages.create.call_args[1]
        assert call_kwargs["max_tokens"] == 8192

    def test_assistant_tool_calls_converted(self):
        """Assistant messages with tool_calls are converted to tool_use blocks."""
        messages = [
            {"role": "user", "content": "Do something"},
            {
                "role": "assistant",
                "content": "I'll help",
                "tool_calls": [
                    {
                        "id": "tc_1",
                        "type": "function",
                        "function": {
                            "name": "read_file",
                            "arguments": '{"path": "test.py"}',
                        },
                    }
                ],
            },
        ]
        _, converted = AnthropicProvider._convert_messages(messages)

        assert len(converted) == 2
        assistant_msg = converted[1]
        assert assistant_msg["role"] == "assistant"
        blocks = assistant_msg["content"]
        assert blocks[0] == {"type": "text", "text": "I'll help"}
        assert blocks[1]["type"] == "tool_use"
        assert blocks[1]["id"] == "tc_1"
        assert blocks[1]["name"] == "read_file"
        assert blocks[1]["input"] == {"path": "test.py"}

    def test_empty_system_messages_skipped(self):
        """Empty system messages are skipped."""
        messages = [
            {"role": "system", "content": ""},
            {"role": "user", "content": "Hi"},
        ]
        system, converted = AnthropicProvider._convert_messages(messages)
        assert system == ""
        assert len(converted) == 1


class TestCreateLLMProvider:
    """Test the create_llm_provider factory."""

    @patch("ayder_cli.services.llm.OpenAI")
    def test_returns_openai_for_openai_provider(self, mock_openai_cls):
        """Factory returns OpenAIProvider when config.provider is 'openai'."""
        config = Mock()
        config.provider = "openai"
        config.base_url = "http://localhost:11434/v1"
        config.api_key = "test-key"

        provider = create_llm_provider(config)
        assert isinstance(provider, OpenAIProvider)

    @patch("ayder_cli.services.llm.AnthropicProvider.__init__", return_value=None)
    def test_returns_anthropic_for_anthropic_provider(self, mock_init):
        """Factory returns AnthropicProvider when config.provider is 'anthropic'."""
        config = Mock()
        config.provider = "anthropic"
        config.api_key = "sk-ant-test"

        provider = create_llm_provider(config)
        assert isinstance(provider, AnthropicProvider)
        mock_init.assert_called_once_with(api_key="sk-ant-test")

    @patch("ayder_cli.services.llm.GeminiProvider.__init__", return_value=None)
    def test_returns_gemini_for_gemini_provider(self, mock_init):
        """Factory returns GeminiProvider when config.provider is 'gemini'."""
        config = Mock()
        config.provider = "gemini"
        config.api_key = "gemini-key"

        # Mock ImportError if google-generativeai is not installed, 
        # or just assume it works if we mock the class.
        # Since we are mocking GeminiProvider, we can assume success.
        
        provider = create_llm_provider(config)
        
        # We need to import GeminiProvider to check isinstance if it wasn't mocked out completely
        # But we mocked __init__. The class itself is still the real class or a mock?
        # The patch decorator patches the class's __init__ method.
        # So provider is an instance of GeminiProvider.
        from ayder_cli.services.llm import GeminiProvider
        assert isinstance(provider, GeminiProvider)
        mock_init.assert_called_once_with(api_key="gemini-key")

    @patch("ayder_cli.services.llm.OpenAI")
    def test_defaults_to_openai_when_no_provider(self, mock_openai_cls):
        """Factory defaults to OpenAI when config has no provider attribute."""
        config = Mock(spec=[])  # no attributes
        config.base_url = "http://localhost:11434/v1"
        config.api_key = "key"

        provider = create_llm_provider(config)
        assert isinstance(provider, OpenAIProvider)
