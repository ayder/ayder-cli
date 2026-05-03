"""Tests for OllamaInspector — model introspection via native ollama SDK."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from ollama import ResponseError

from ayder_cli.providers.impl.ollama_inspector import (
    ModelInfo,
    NativeToolProbe,
    OllamaInspector,
    RuntimeState,
)


@pytest.fixture
def mock_client():
    return AsyncMock()


@pytest.fixture
def inspector(mock_client):
    with patch("ayder_cli.providers.impl.ollama_inspector.AsyncClient", return_value=mock_client):
        return OllamaInspector(host="http://localhost:11434")


def test_model_info_has_name_field_with_empty_default():
    info = ModelInfo()
    assert info.name == ""


@pytest.mark.asyncio
async def test_get_model_info_extracts_context_length(inspector, mock_client):
    """Should find context_length from family-prefixed key in modelinfo."""
    mock_response = MagicMock()
    mock_response.modelinfo = {"qwen2.context_length": 131072, "qwen2.embedding_length": 3584}
    mock_response.capabilities = ["completion", "tools"]
    mock_response.details = MagicMock()
    mock_response.details.family = "qwen2"
    mock_response.details.quantization_level = "Q4_K_M"
    mock_client.show.return_value = mock_response

    info = await inspector.get_model_info("qwen3-coder:latest")

    assert info.name == "qwen3-coder:latest"
    assert info.max_context_length == 131072
    assert info.family == "qwen2"
    assert info.quantization == "Q4_K_M"
    assert "tools" in info.capabilities
    mock_client.show.assert_awaited_once_with("qwen3-coder:latest")


@pytest.mark.asyncio
async def test_get_model_info_different_family_prefix(inspector, mock_client):
    """Should handle different model families (llama, gemma, etc.)."""
    mock_response = MagicMock()
    mock_response.modelinfo = {"llama.context_length": 8192, "llama.attention.head_count": 32}
    mock_response.capabilities = ["completion"]
    mock_response.details = MagicMock()
    mock_response.details.family = "llama"
    mock_response.details.quantization_level = "Q8_0"
    mock_client.show.return_value = mock_response

    info = await inspector.get_model_info("llama3:8b")

    assert info.max_context_length == 8192
    assert info.family == "llama"


@pytest.mark.asyncio
async def test_get_model_info_no_context_length_key(inspector, mock_client):
    """Should return 0 if no context_length key found in modelinfo."""
    mock_response = MagicMock()
    mock_response.modelinfo = {"some.other_key": 42}
    mock_response.capabilities = None
    mock_response.details = MagicMock()
    mock_response.details.family = "unknown"
    mock_response.details.quantization_level = ""
    mock_client.show.return_value = mock_response

    info = await inspector.get_model_info("custom:latest")

    assert info.max_context_length == 0
    assert info.capabilities == []


@pytest.mark.asyncio
async def test_get_runtime_state(inspector, mock_client):
    """Should extract context_length, expires_at, and vram from ps response."""
    mock_model = MagicMock()
    mock_model.context_length = 65536
    mock_model.expires_at = datetime(2026, 3, 23, 12, 0, 0)
    mock_model.size_vram = 22_000_000_000

    mock_ps = MagicMock()
    mock_ps.models = [mock_model]
    mock_client.ps.return_value = mock_ps

    state = await inspector.get_runtime_state()

    assert state.active_context_length == 65536
    assert state.expires_at == datetime(2026, 3, 23, 12, 0, 0)
    assert state.vram_used == 22_000_000_000


@pytest.mark.asyncio
async def test_get_runtime_state_no_models(inspector, mock_client):
    """Should return defaults when no models are running."""
    mock_ps = MagicMock()
    mock_ps.models = []
    mock_client.ps.return_value = mock_ps

    state = await inspector.get_runtime_state()

    assert state.active_context_length == 0
    assert state.expires_at is None
    assert state.vram_used == 0


@pytest.mark.asyncio
async def test_get_model_info_connection_error(inspector, mock_client):
    """Should raise on connection failure — caller handles fallback."""
    mock_client.show.side_effect = ConnectionError("refused")

    with pytest.raises(ConnectionError):
        await inspector.get_model_info("any:model")


def _chat_response(content: str = "", tool_calls=None):
    """Build a fake non-streaming /api/chat response."""
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls or []
    resp = MagicMock()
    resp.message = msg
    return resp


@pytest.mark.asyncio
async def test_probe_native_tool_calling_native_works(inspector, mock_client):
    """Empty/clean content + populated tool_calls = native_works."""
    fake_tc = MagicMock(id="call_1")
    fake_tc.function = MagicMock(name="read_file", arguments={"path": "/tmp/x"})
    mock_client.chat.return_value = _chat_response(content="", tool_calls=[fake_tc])

    probe = await inspector.probe_native_tool_calling("any-model")

    assert probe.verdict == "native_works"
    assert probe.tool_call_count == 1
    assert probe.content_markup_found == []


@pytest.mark.asyncio
async def test_probe_native_tool_calling_detects_dsml_leak(inspector, mock_client):
    """The exact deepseek-v4-pro:cloud symptom: <｜DSML｜tool_calls> in content."""
    leaked = (
        "Calling tool:\n"
        "<｜ＤＳＭＬ｜tool_calls>"
        "<｜ＤＳＭＬ｜invoke name=\"read_file\">"
        "<｜ＤＳＭＬ｜parameter name=\"path\">/tmp/x</｜ＤＳＭＬ｜parameter>"
        "</｜ＤＳＭＬ｜invoke>"
        "</｜ＤＳＭＬ｜tool_calls>"
    )
    mock_client.chat.return_value = _chat_response(content=leaked)

    probe = await inspector.probe_native_tool_calling("deepseek-broken")

    assert probe.verdict == "leaks_in_content"
    # The DSML marker is the strongest signal — it interposes between the
    # raw `<` and the tag name `invoke`, so the bare `<invoke` regex won't
    # match. The DSML detection alone is enough to flag the leak.
    assert "｜DSML｜" in probe.content_markup_found


@pytest.mark.asyncio
async def test_probe_native_tool_calling_detects_function_calls_leak(inspector, mock_client):
    """deepseek-r1/v3 style without DSML markers."""
    leaked = (
        "<function_calls>"
        "<invoke name=\"read_file\">"
        "<parameter name=\"path\">/tmp/x</parameter>"
        "</invoke>"
        "</function_calls>"
    )
    mock_client.chat.return_value = _chat_response(content=leaked)

    probe = await inspector.probe_native_tool_calling("deepseek-r1")

    assert probe.verdict == "leaks_in_content"
    assert "<function_calls>" in probe.content_markup_found


@pytest.mark.asyncio
async def test_probe_native_tool_calling_detects_tool_call_singular_leak(
    inspector, mock_client
):
    """qwen3-trained <tool_call>{json}</tool_call> in content."""
    leaked = '<tool_call>{"name": "read_file", "arguments": {"path": "/tmp/x"}}</tool_call>'
    mock_client.chat.return_value = _chat_response(content=leaked)

    probe = await inspector.probe_native_tool_calling("qwen-broken")

    assert probe.verdict == "leaks_in_content"
    assert "<tool_call>" in probe.content_markup_found


@pytest.mark.asyncio
async def test_probe_native_tool_calling_no_tool_call(inspector, mock_client):
    """Model produced narration only — neither tool_calls nor markup."""
    mock_client.chat.return_value = _chat_response(content="I would read the file.")

    probe = await inspector.probe_native_tool_calling("any-model")

    assert probe.verdict == "no_tool_call"
    assert probe.tool_call_count == 0
    assert probe.content_markup_found == []


@pytest.mark.asyncio
async def test_probe_native_tool_calling_handles_response_error(inspector, mock_client):
    """Probe failures bubble out as a stream_failed verdict."""
    mock_client.chat.side_effect = ResponseError("EOF (status code: -1)")

    probe = await inspector.probe_native_tool_calling("any-model")

    assert probe.verdict == "stream_failed"
    assert "EOF" in probe.raw_error
