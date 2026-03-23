"""Tests for the native OllamaProvider built on ollama.AsyncClient."""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from ollama._types import Message as OllamaMessage

from ayder_cli.providers.impl.ollama import OllamaProvider
from ayder_cli.providers.base import NormalizedStreamChunk, ToolCallDef


def make_config(**overrides):
    """Create a minimal config mock for OllamaProvider."""
    cfg = MagicMock()
    cfg.base_url = "http://localhost:11434"
    cfg.chat_protocol = "ollama"
    cfg.api_key = ""
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


def make_chat_response(content="", thinking="", tool_calls=None, done=False, **timing):
    """Create a mock ollama ChatResponse."""
    msg = MagicMock()
    msg.content = content
    msg.thinking = thinking
    msg.tool_calls = tool_calls or []

    resp = MagicMock()
    resp.message = msg
    resp.done = done
    resp.prompt_eval_count = timing.get("prompt_eval_count")
    resp.prompt_eval_duration = timing.get("prompt_eval_duration")
    resp.eval_count = timing.get("eval_count")
    resp.eval_duration = timing.get("eval_duration")
    resp.load_duration = timing.get("load_duration")
    return resp


@pytest.mark.asyncio
async def test_stream_yields_content_chunks():
    """Native streaming should yield content from each ChatResponse."""
    chunks = [
        make_chat_response(content="Hello"),
        make_chat_response(content=" world"),
        make_chat_response(content="!", done=True, prompt_eval_count=10,
                          prompt_eval_duration=5000, eval_count=3, eval_duration=1000,
                          load_duration=0),
    ]

    cfg = make_config()

    async def mock_stream(*args, **kwargs):
        for c in chunks:
            yield c

    with patch("ayder_cli.providers.impl.ollama.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.chat.return_value = mock_stream()
        MockClient.return_value = instance

        provider = OllamaProvider(cfg)
        results = []
        async for chunk in provider.stream_with_tools(
            messages=[{"role": "user", "content": "hi"}],
            model="test:latest",
            tools=None,
            options={"num_ctx": 8192},
        ):
            results.append(chunk)

    assert len(results) == 3
    assert results[0].content == "Hello"
    assert results[1].content == " world"
    # Final chunk should have usage with timing data
    assert results[2].usage is not None
    assert results[2].usage["prompt_tokens"] == 10
    assert results[2].usage["prompt_eval_ns"] == 5000


@pytest.mark.asyncio
async def test_stream_extracts_thinking():
    """Native thinking via message.thinking field should map to reasoning."""
    chunks = [
        make_chat_response(thinking="Let me think..."),
        make_chat_response(content="The answer is 42", done=True,
                          prompt_eval_count=5, eval_count=6,
                          prompt_eval_duration=100, eval_duration=200,
                          load_duration=0),
    ]

    cfg = make_config()

    async def mock_stream(*args, **kwargs):
        for c in chunks:
            yield c

    with patch("ayder_cli.providers.impl.ollama.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.chat.return_value = mock_stream()
        MockClient.return_value = instance

        provider = OllamaProvider(cfg)
        results = []
        async for chunk in provider.stream_with_tools(
            messages=[{"role": "user", "content": "think"}],
            model="test:latest",
        ):
            results.append(chunk)

    assert results[0].reasoning == "Let me think..."
    assert results[1].content == "The answer is 42"


@pytest.mark.asyncio
async def test_stream_extracts_native_tool_calls():
    """Native tool calls from Message.tool_calls should map to ToolCallDef."""
    tool_call = MagicMock()
    tool_call.function.name = "read_file"
    tool_call.function.arguments = {"file_path": "/tmp/test.py"}

    chunks = [
        make_chat_response(tool_calls=[tool_call], done=True,
                          prompt_eval_count=20, eval_count=10,
                          prompt_eval_duration=500, eval_duration=300,
                          load_duration=0),
    ]

    cfg = make_config()

    async def mock_stream(*args, **kwargs):
        for c in chunks:
            yield c

    with patch("ayder_cli.providers.impl.ollama.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.chat.return_value = mock_stream()
        MockClient.return_value = instance

        provider = OllamaProvider(cfg)
        results = []
        async for chunk in provider.stream_with_tools(
            messages=[{"role": "user", "content": "read"}],
            model="test:latest",
            tools=[{"type": "function", "function": {"name": "read_file"}}],
        ):
            results.append(chunk)

    final = results[-1]
    assert len(final.tool_calls) == 1
    assert final.tool_calls[0].name == "read_file"
    assert json.loads(final.tool_calls[0].arguments) == {"file_path": "/tmp/test.py"}


@pytest.mark.asyncio
async def test_list_models():
    """list_models should use native client.list()."""
    cfg = make_config()

    mock_model_1 = MagicMock()
    mock_model_1.model = "qwen3:latest"
    mock_model_2 = MagicMock()
    mock_model_2.model = "llama3:8b"

    mock_response = MagicMock()
    mock_response.models = [mock_model_1, mock_model_2]

    with patch("ayder_cli.providers.impl.ollama.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.list.return_value = mock_response
        MockClient.return_value = instance

        provider = OllamaProvider(cfg)
        models = await provider.list_models()

    assert models == ["qwen3:latest", "llama3:8b"]


@pytest.mark.asyncio
async def test_keep_alive_set_to_infinite():
    """Every chat call should set keep_alive=-1."""
    cfg = make_config()

    async def mock_stream(*args, **kwargs):
        yield make_chat_response(content="ok", done=True,
                                prompt_eval_count=1, eval_count=1,
                                prompt_eval_duration=10, eval_duration=10,
                                load_duration=0)

    with patch("ayder_cli.providers.impl.ollama.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.chat.return_value = mock_stream()
        MockClient.return_value = instance

        provider = OllamaProvider(cfg)
        async for _ in provider.stream_with_tools(
            messages=[{"role": "user", "content": "test"}],
            model="test:latest",
            options={"num_ctx": 4096},
        ):
            pass

        call_kwargs = instance.chat.call_args
        assert call_kwargs.kwargs.get("keep_alive") == -1 or call_kwargs[1].get("keep_alive") == -1


# =============================================================================
# SDK Compliance Regression Tests
# =============================================================================
# These tests validate _convert_messages output against the REAL ollama SDK's
# Message.model_validate(). If the SDK ever changes validation rules, these
# tests break here — not in production.


class TestConvertMessagesSDKCompliance:
    """Validate _convert_messages against ollama SDK's Message.model_validate()."""

    def _provider(self):
        cfg = make_config()
        with patch("ayder_cli.providers.impl.ollama.AsyncClient"):
            return OllamaProvider(cfg)

    def _convert(self, messages):
        return self._provider()._convert_messages(messages)

    def _validate_through_sdk(self, messages):
        """Run messages through the same pipeline as ollama._client._copy_messages."""
        converted = self._convert(messages)
        validated = []
        for msg in converted:
            filtered = {k: v for k, v in msg.items() if v}
            validated.append(OllamaMessage.model_validate(filtered))
        return validated

    def test_system_message(self):
        result = self._validate_through_sdk([{"role": "system", "content": "You are helpful."}])
        assert result[0].role == "system"
        assert result[0].content == "You are helpful."

    def test_user_message(self):
        result = self._validate_through_sdk([{"role": "user", "content": "Hello"}])
        assert result[0].role == "user"
        assert result[0].content == "Hello"

    def test_assistant_text_only(self):
        result = self._validate_through_sdk([{"role": "assistant", "content": "Hi there!"}])
        assert result[0].role == "assistant"
        assert result[0].content == "Hi there!"

    def test_assistant_with_tool_calls_json_string_args(self):
        """Arguments stored as JSON string in history must be converted to dict."""
        msgs = [{
            "role": "assistant",
            "content": "",
            "tool_calls": [{
                "id": "call_0",
                "type": "function",
                "function": {
                    "name": "read_file",
                    "arguments": '{"path": "/tmp/test.py"}',
                },
            }],
        }]
        result = self._validate_through_sdk(msgs)
        assert result[0].tool_calls is not None
        assert len(result[0].tool_calls) == 1
        assert result[0].tool_calls[0].function.name == "read_file"
        assert result[0].tool_calls[0].function.arguments == {"path": "/tmp/test.py"}

    def test_assistant_with_dict_arguments(self):
        """Arguments already as dict should pass through."""
        msgs = [{
            "role": "assistant",
            "content": "",
            "tool_calls": [{
                "id": "call_0",
                "type": "function",
                "function": {"name": "run_command", "arguments": {"command": "ls"}},
            }],
        }]
        result = self._validate_through_sdk(msgs)
        assert result[0].tool_calls[0].function.arguments == {"command": "ls"}

    def test_tool_result_uses_tool_name(self):
        """Tool result must map 'name' → 'tool_name' for SDK compliance."""
        msgs = [{
            "role": "tool",
            "tool_call_id": "call_0",
            "name": "read_file",
            "content": "file contents here",
        }]
        result = self._validate_through_sdk(msgs)
        assert result[0].role == "tool"
        assert result[0].content == "file contents here"
        assert result[0].tool_name == "read_file"

    def test_tool_result_empty_content(self):
        """Tool result with empty content should validate (content becomes None)."""
        msgs = [{"role": "tool", "name": "run_command", "content": ""}]
        result = self._validate_through_sdk(msgs)
        assert result[0].role == "tool"
        assert result[0].tool_name == "run_command"

    def test_full_tool_call_cycle(self):
        """Complete cycle: system → user → assistant(tool_call) → tool → assistant."""
        msgs = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "List files"},
            {
                "role": "assistant", "content": "",
                "tool_calls": [{
                    "id": "call_0", "type": "function",
                    "function": {"name": "file_explorer", "arguments": '{"path": "."}'},
                }],
            },
            {
                "role": "tool", "tool_call_id": "call_0",
                "name": "file_explorer", "content": '["file1.py"]',
            },
            {"role": "assistant", "content": "I found 1 file."},
        ]
        result = self._validate_through_sdk(msgs)
        assert len(result) == 5

    def test_multiple_tool_calls(self):
        """Assistant with multiple parallel tool calls."""
        msgs = [{
            "role": "assistant", "content": "",
            "tool_calls": [
                {"id": "call_0", "type": "function",
                 "function": {"name": "read_file", "arguments": '{"path": "a.py"}'}},
                {"id": "call_1", "type": "function",
                 "function": {"name": "read_file", "arguments": '{"path": "b.py"}'}},
            ],
        }]
        result = self._validate_through_sdk(msgs)
        assert len(result[0].tool_calls) == 2

    def test_malformed_json_arguments_uses_empty_dict(self):
        """Malformed JSON arguments should be replaced with empty dict (logged as warning)."""
        msgs = [{
            "role": "assistant", "content": "",
            "tool_calls": [{
                "id": "call_0", "type": "function",
                "function": {"name": "test_tool", "arguments": "not json {{{"},
            }],
        }]
        result = self._validate_through_sdk(msgs)
        assert result[0].tool_calls[0].function.arguments == {}

    def test_dummy_tool_calls_filtered(self):
        """Dummy tool calls with empty name (from streaming gaps) should be filtered."""
        msgs = [{
            "role": "assistant", "content": "",
            "tool_calls": [
                {"id": "dummy_0", "type": "function",
                 "function": {"name": "", "arguments": ""}},
                {"id": "call_1", "type": "function",
                 "function": {"name": "read_file", "arguments": '{"path": "x"}'}},
            ],
        }]
        result = self._validate_through_sdk(msgs)
        assert len(result[0].tool_calls) == 1
        assert result[0].tool_calls[0].function.name == "read_file"

    def test_reasoning_content_ignored_by_sdk(self):
        """reasoning_content from history should not cause SDK validation error."""
        msgs = [{
            "role": "assistant", "content": "Hello",
            "reasoning_content": "I thought about this...",
        }]
        result = self._validate_through_sdk(msgs)
        assert result[0].content == "Hello"

    def test_whitespace_only_tool_name_filtered(self):
        """Tool calls with whitespace-only name should be filtered."""
        msgs = [{
            "role": "assistant", "content": "",
            "tool_calls": [{
                "id": "call_0", "type": "function",
                "function": {"name": "   ", "arguments": '{"a": 1}'},
            }],
        }]
        result = self._validate_through_sdk(msgs)
        assert result[0].tool_calls is None  # All filtered → no tool_calls field
