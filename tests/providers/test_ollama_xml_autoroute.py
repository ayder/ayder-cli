"""Tests for Ollama XML-fallback auto-detection.

Background: DeepSeek models on Ollama emit tool calls as XML text inside
`msg.content` (e.g. <function_calls><invoke name="...">...</invoke></function_calls>)
instead of using Ollama's native `msg.tool_calls` channel. Before this fix,
the native code path forwarded that text raw to the chat UI. The matcher
below identifies model names that are known to need the XML fallback so the
provider can auto-upgrade its routing.
"""
import pytest

from ayder_cli.providers.impl.ollama import _requires_xml_fallback


@pytest.mark.parametrize("model", [
    "deepseek-r1",
    "deepseek-r1:latest",
    "deepseek-r1:7b",
    "deepseek-r1:32b-instruct",
    "deepseek-v3",
    "deepseek-v3:latest",
    "deepseek-v3.2",
    "deepseek-v3.2:latest",
    "deepseek-coder",
    "deepseek-coder-v2:16b",
    "minimax-m1",
    "minimax-m1:latest",
    # qwen2/qwen3 server-side XML extractor crashes on truncated tool calls
    # ("XML syntax error: unexpected EOF") — must route through in-house parser.
    "qwen3",
    "qwen3:6b",
    "qwen3.6",
    "qwen3.6:latest",
    "qwen3-coder:latest",
    "qwen2",
    "qwen2.5-coder:7b",
    # Case insensitive — Ollama model tags often mix cases
    "DeepSeek-R1",
    "MiniMax-M1",
    "Qwen3-Coder",
])
def test_requires_xml_fallback_matches_known_families(model):
    assert _requires_xml_fallback(model) is True, (
        f"Expected {model!r} to require XML fallback"
    )


@pytest.mark.parametrize("model", [
    "llama3.1:8b",
    "llama3.3:70b",
    "mistral-nemo:latest",
    "gemma2:27b",
    "phi4:latest",
    "",  # empty string must not match
])
def test_requires_xml_fallback_rejects_other_models(model):
    assert _requires_xml_fallback(model) is False, (
        f"Expected {model!r} NOT to require XML fallback"
    )


def test_requires_xml_fallback_handles_registry_prefix():
    """Ollama models can be pulled with an owner prefix (e.g. hf.co/...).
    The matcher should still recognize the family by substring."""
    assert _requires_xml_fallback("hf.co/deepseek-ai/deepseek-r1-7b") is True
    assert _requires_xml_fallback("registry.example/deepseek-v3.2:q4") is True


import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from ayder_cli.providers.impl.ollama import OllamaProvider, XML_INSTRUCTION  # noqa: E402,F401


def _config(model: str, chat_protocol: str = "ollama"):
    cfg = MagicMock()
    cfg.base_url = "http://localhost:11434"
    cfg.api_key = ""
    cfg.model = model
    cfg.chat_protocol = chat_protocol
    return cfg


def _mock_chunk(content="", thinking="", done=False, tool_calls=None):
    msg = MagicMock()
    msg.content = content
    msg.thinking = thinking
    msg.tool_calls = tool_calls or []
    resp = MagicMock()
    resp.message = msg
    resp.done = done
    resp.prompt_eval_count = 5 if done else None
    resp.prompt_eval_duration = 100 if done else None
    resp.eval_count = 3 if done else None
    resp.eval_duration = 50 if done else None
    resp.load_duration = 0 if done else None
    return resp


def _drive_stream_and_capture(model: str, chat_protocol: str):
    """Run OllamaProvider.stream_with_tools with mocked AsyncClient and
    return the list of messages the provider forwarded to client.chat()."""
    captured_messages: list = []

    async def _run():
        async def fake_mock_stream():
            yield _mock_chunk(content="ok", done=True)

        async def fake_chat(*args, **kwargs):
            captured_messages.extend(kwargs.get("messages", []))
            return fake_mock_stream()

        with patch("ayder_cli.providers.impl.ollama.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.chat.side_effect = fake_chat
            MockClient.return_value = instance

            provider = OllamaProvider(_config(model, chat_protocol=chat_protocol))
            async for _ in provider.stream_with_tools(
                messages=[{"role": "system", "content": "base"},
                          {"role": "user", "content": "hi"}],
                model=model,
                tools=[{"type": "function",
                        "function": {"name": "read_file"}}],
            ):
                pass

    asyncio.run(_run())
    return captured_messages


def test_deepseek_model_auto_routes_to_xml_fallback():
    """When chat_protocol='ollama' (default) and model is DeepSeek, the
    provider MUST route through _stream_xml_fallback — which is detectable
    by the XML_INSTRUCTION being injected into the system prompt sent to
    the Ollama client."""
    captured_messages = _drive_stream_and_capture(
        "deepseek-v3.2:latest", chat_protocol="ollama"
    )

    # The XML fallback injects XML_INSTRUCTION into the system message.
    # If native path ran, no such injection would appear.
    system_msg = next((m for m in captured_messages if m.get("role") == "system"), None)
    assert system_msg is not None
    assert "XML format for all tool calls" in system_msg["content"], (
        "Expected XML_INSTRUCTION to be injected — confirms _stream_xml_fallback ran"
    )


def test_llama_model_stays_on_native_path():
    """When the matcher does not trip, native path runs — no XML_INSTRUCTION
    injection occurs."""
    captured_messages = _drive_stream_and_capture(
        "llama3.1:8b", chat_protocol="ollama"
    )

    system_msg = next((m for m in captured_messages if m.get("role") == "system"), None)
    assert system_msg is not None
    assert "XML format for all tool calls" not in system_msg["content"], (
        "Expected native path — no XML_INSTRUCTION should have been injected"
    )


def test_explicit_chat_protocol_xml_always_runs_xml_fallback():
    """chat_protocol='xml' must keep running the XML fallback regardless of
    model (preserves existing behavior for users who opted in)."""
    captured_messages = _drive_stream_and_capture(
        "llama3.1:8b", chat_protocol="xml"
    )

    system_msg = next((m for m in captured_messages if m.get("role") == "system"), None)
    assert system_msg is not None
    assert "XML format for all tool calls" in system_msg["content"]
