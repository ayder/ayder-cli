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
    # Case insensitive — Ollama model tags often mix cases
    "DeepSeek-R1",
    "MiniMax-M1",
])
def test_requires_xml_fallback_matches_known_families(model):
    assert _requires_xml_fallback(model) is True, (
        f"Expected {model!r} to require XML fallback"
    )


@pytest.mark.parametrize("model", [
    "qwen3-coder:latest",  # Qwen3 has working native tool calling on Ollama
    "qwen2.5-coder:7b",
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
