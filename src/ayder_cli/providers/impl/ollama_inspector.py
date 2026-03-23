"""Ollama model introspection via native SDK.

Wraps ollama.AsyncClient for /api/show and /api/ps calls.
Used by OllamaContextManager to auto-detect context length and cache TTL.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from ollama import AsyncClient


@dataclass
class ModelInfo:
    """Model metadata from /api/show."""
    max_context_length: int = 0
    capabilities: list[str] = field(default_factory=list)
    quantization: str = ""
    family: str = ""


@dataclass
class RuntimeState:
    """Running model state from /api/ps."""
    active_context_length: int = 0
    expires_at: Optional[datetime] = None
    vram_used: int = 0


class OllamaInspector:
    """Queries Ollama for model metadata and runtime state."""

    def __init__(self, host: str = "http://localhost:11434"):
        self._client = AsyncClient(host=host)

    async def get_model_info(self, model: str) -> ModelInfo:
        """Call /api/show to get model context length, capabilities, etc."""
        response = await self._client.show(model)

        # Extract context_length from modelinfo dict.
        # Key is family-prefixed: "qwen2.context_length", "llama.context_length", etc.
        max_ctx = 0
        modelinfo = response.modelinfo or {}
        for key, value in modelinfo.items():
            if key.endswith(".context_length") and isinstance(value, int):
                max_ctx = value
                break

        capabilities = list(response.capabilities) if response.capabilities else []
        details = response.details
        family = getattr(details, "family", "") or ""
        quantization = getattr(details, "quantization_level", "") or ""

        return ModelInfo(
            max_context_length=max_ctx,
            capabilities=capabilities,
            quantization=quantization,
            family=family,
        )

    async def get_runtime_state(self) -> RuntimeState:
        """Call /api/ps to get running model state."""
        response = await self._client.ps()

        if not response.models:
            return RuntimeState()

        model = response.models[0]
        return RuntimeState(
            active_context_length=model.context_length or 0,
            expires_at=model.expires_at,
            vram_used=int(model.size_vram) if model.size_vram else 0,
        )
