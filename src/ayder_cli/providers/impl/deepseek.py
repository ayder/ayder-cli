"""
DeepSeek Provider implementation.
"""

from typing import Any, AsyncGenerator, Dict, List, Optional

from ayder_cli.core.config import Config
from ayder_cli.providers.base import (
    AIProvider,
    NormalizedStreamChunk,
)
from ayder_cli.providers.impl.openai import OpenAIProvider


class DeepSeekProvider(AIProvider):
    """
    Provider for DeepSeek models.
    DeepSeek handles native tool calling but often mixes <think> tags in the stream.
    """

    def __init__(self, config: Config, interaction_sink=None):
        self.config = config
        self.interaction_sink = interaction_sink
        # DeepSeek uses OpenAI-compatible API with legacy max_tokens
        self.base_provider = OpenAIProvider(config, interaction_sink=interaction_sink)
        self.base_provider.MAX_TOKENS_PARAM = "max_tokens"

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        options: Optional[Dict[str, Any]] = None,
        verbose: bool = False,
    ) -> NormalizedStreamChunk:
        return await self.base_provider.chat(messages, model, tools, options, verbose)

    async def stream_with_tools(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        options: Optional[Dict[str, Any]] = None,
        verbose: bool = False,
    ) -> AsyncGenerator[NormalizedStreamChunk, None]:
        
        async_stream = self.base_provider.stream_with_tools(
            messages, model, tools, options, verbose
        )

        async for chunk in async_stream:
            # DeepSeek might put reasoning in reasoning_content or within <think> tags in content.
            # OpenAIProvider already captures reasoning_content.
            # If it's in <think> tags, we might want to split it here or let the UI handle it.
            # For now, we trust the OpenAIProvider's base normalization.
            yield chunk
