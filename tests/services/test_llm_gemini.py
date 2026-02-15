import json
import pytest
from unittest.mock import Mock, patch, MagicMock
from ayder_cli.services.llm import GeminiProvider, _Response

class TestGeminiProvider:
    """Test GeminiProvider with google-genai SDK."""

    def test_init_with_injected_client(self):
        """Constructor uses injected client when provided."""
        mock_client = Mock()
        provider = GeminiProvider(client=mock_client)
        assert provider.client is mock_client

    def test_convert_messages_basic(self):
        """Test basic message conversion."""
        messages = [
            {"role": "system", "content": "Be helpful"},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ]
        system, converted = GeminiProvider._convert_messages(messages)
        
        assert system == "Be helpful"
        assert len(converted) == 2
        assert converted[0]["role"] == "user"
        assert converted[0]["parts"][0]["text"] == "Hello"
        assert converted[1]["role"] == "model"
        assert converted[1]["parts"][0]["text"] == "Hi there"

    def test_convert_messages_tool_calls(self):
        """Test converting assistant tool calls."""
        messages = [
            {
                "role": "assistant",
                "content": "I will check",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "function": {
                            "name": "check_weather",
                            "arguments": '{"city": "Paris"}'
                        }
                    }
                ]
            }
        ]
        _, converted = GeminiProvider._convert_messages(messages)
        
        assert len(converted) == 1
        msg = converted[0]
        assert msg["role"] == "model"
        assert len(msg["parts"]) == 2
        assert msg["parts"][0]["text"] == "I will check"
        fc = msg["parts"][1]["function_call"]
        assert fc["name"] == "check_weather"
        assert fc["args"] == {"city": "Paris"}

    def test_convert_messages_tool_result(self):
        """Test converting tool results."""
        messages = [
            {"role": "tool", "tool_call_id": "call_1", "name": "check_weather", "content": '{"temp": 15}'}
        ]
        _, converted = GeminiProvider._convert_messages(messages)
        
        assert len(converted) == 1
        msg = converted[0]
        # In new SDK, tool response role is 'user'
        assert msg["role"] == "user"
        part = msg["parts"][0]["function_response"]
        assert part["name"] == "check_weather"
        assert part["response"] == {"temp": 15}

    def test_convert_messages_merge_consecutive(self):
        """Test merging consecutive messages."""
        messages = [
            {"role": "user", "content": "Part 1"},
            {"role": "user", "content": "Part 2"},
        ]
        _, converted = GeminiProvider._convert_messages(messages)
        
        assert len(converted) == 1
        assert converted[0]["role"] == "user"
        assert len(converted[0]["parts"]) == 2
        assert converted[0]["parts"][0]["text"] == "Part 1"
        assert converted[0]["parts"][1]["text"] == "Part 2"

    def test_convert_tools(self):
        """Test tool conversion."""
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "test_tool",
                    "description": "A test tool",
                    "parameters": {"type": "object"}
                }
            }
        ]
        g_tools = GeminiProvider._convert_tools(tools)
        
        assert len(g_tools) == 1
        assert "function_declarations" in g_tools[0]
        funcs = g_tools[0]["function_declarations"]
        assert len(funcs) == 1
        assert funcs[0]["name"] == "test_tool"
        assert funcs[0]["description"] == "A test tool"

    def test_wrap_response_text(self):
        """Test wrapping text response."""
        mock_response = Mock()
        mock_candidate = Mock()
        mock_part = Mock()
        mock_part.text = "Response text"
        mock_part.function_call = None
        mock_candidate.content.parts = [mock_part]
        mock_response.candidates = [mock_candidate]
        # Updated to use response_token_count for new SDK
        mock_response.usage_metadata.prompt_token_count = 10
        mock_response.usage_metadata.response_token_count = 20 
        mock_response.usage_metadata.candidates_token_count = None # Mock absence or older SDK compatibility check

        wrapped = GeminiProvider._wrap_response(mock_response)
        
        assert wrapped.choices[0].message.content == "Response text"
        assert wrapped.usage.total_tokens == 30

    def test_wrap_response_tool_call(self):
        """Test wrapping tool call response."""
        mock_response = Mock()
        mock_candidate = Mock()
        mock_part = Mock()
        mock_part.text = None
        mock_part.function_call = Mock(name="test_tool", args={"a": 1})
        mock_part.function_call.name = "test_tool" # Mock quirk
        mock_candidate.content.parts = [mock_part]
        mock_response.candidates = [mock_candidate]
        mock_response.usage_metadata = None

        wrapped = GeminiProvider._wrap_response(mock_response)
        
        msg = wrapped.choices[0].message
        assert msg.content is None
        assert len(msg.tool_calls) == 1
        tc = msg.tool_calls[0]
        assert tc.function.name == "test_tool"
        assert json.loads(tc.function.arguments) == {"a": 1}
        assert tc.id.startswith("call_")

    def test_chat_calls_generate_content(self):
        """Test chat method calls client.models.generate_content."""
        mock_client = Mock()
        mock_response = Mock()
        mock_response.candidates = [Mock(content=Mock(parts=[Mock(text="response", function_call=None)]))]
        # Updated usage tokens
        mock_response.usage_metadata.prompt_token_count = 10
        mock_response.usage_metadata.response_token_count = 20
        mock_response.usage_metadata.candidates_token_count = None
        mock_client.models.generate_content.return_value = mock_response

        provider = GeminiProvider(client=mock_client)
        messages = [{"role": "user", "content": "hello"}]
        
        provider.chat(messages, model="gemini-3-flash")
        
        mock_client.models.generate_content.assert_called_once()
        # Verify kwargs
        call_kwargs = mock_client.models.generate_content.call_args[1]
        assert call_kwargs["model"] == "gemini-3-flash"
        assert len(call_kwargs["contents"]) == 1
        assert "config" in call_kwargs

    def test_list_models(self):
        """Test list_models."""
        mock_client = Mock()
        m1 = Mock()
        m1.name = "models/gemini-3-pro"
        m1.supported_actions = ["generateContent"]
        m2 = Mock()
        m2.name = "models/embedding-001"
        m2.supported_actions = ["embedContent"]
        
        mock_client.models.list.return_value = [m1, m2]
        
        provider = GeminiProvider(client=mock_client)
        models = provider.list_models()
        
        assert "gemini-3-pro" in models
        assert "embedding-001" not in models
