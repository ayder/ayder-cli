"""Tests for OllamaInspector — model introspection via native ollama SDK."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from ayder_cli.providers.impl.ollama_inspector import (
    OllamaInspector,
    ModelInfo,
    RuntimeState,
)


@pytest.fixture
def mock_client():
    return AsyncMock()


@pytest.fixture
def inspector(mock_client):
    with patch("ayder_cli.providers.impl.ollama_inspector.AsyncClient", return_value=mock_client):
        return OllamaInspector(host="http://localhost:11434")


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
