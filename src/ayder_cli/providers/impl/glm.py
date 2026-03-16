"""
GLM Native Provider implementation using ZhipuAI SDK.
"""

from typing import Any, AsyncGenerator, Dict, List, Optional

from ayder_cli.core.config import Config
from ayder_cli.providers.base import (
    AIProvider,
    NormalizedStreamChunk,
    ToolCallDef,
)


class GLMNativeProvider(AIProvider):
    """
    Provider for ZhipuAI GLM models using the official SDK.
    Natively supports GLM's unique tool schemas and reasoning tokens.
    """

    def __init__(self, config: Config, interaction_sink=None):
        self.config = config
        self.interaction_sink = interaction_sink
        # Lazy import ZhipuAI
        from zhipuai import ZhipuAI
        self.client = ZhipuAI(api_key=config.api_key)

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        options: Optional[Dict[str, Any]] = None,
        verbose: bool = False,
    ) -> NormalizedStreamChunk:
        
        # GLM-5/4 support OpenAI-like tools parameter
        response = self.client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools,
            stream=False,
        )
        return self._normalize_response(response)

    async def stream_with_tools(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        options: Optional[Dict[str, Any]] = None,
        verbose: bool = False,
    ) -> AsyncGenerator[NormalizedStreamChunk, None]:
        
        response_stream = self.client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools,
            stream=True,
        )

        for chunk in response_stream:
            yield self._normalize_chunk(chunk)

    def _normalize_response(self, response: Any) -> NormalizedStreamChunk:
        msg = response.choices[0].message
        content = msg.content or ""
        tool_calls = []
        
        if msg.tool_calls:
            for tc in msg.tool_calls:
                tool_calls.append(
                    ToolCallDef(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=tc.function.arguments
                    )
                )
        
        usage = {"total_tokens": response.usage.total_tokens} if response.usage else None
        return NormalizedStreamChunk(
            content=content,
            tool_calls=tool_calls,
            raw_chunk=response,
            usage=usage
        )

    def _normalize_chunk(self, chunk: Any) -> NormalizedStreamChunk:
        content = ""
        tool_calls = []
        
        if not chunk.choices:
            return NormalizedStreamChunk(raw_chunk=chunk)
            
        delta = chunk.choices[0].delta
        if delta.content:
            content = delta.content
            
        if delta.tool_calls:
            for tc in delta.tool_calls:
                tool_calls.append(
                    ToolCallDef(
                        id=tc.id or "",
                        name=tc.function.name or "",
                        arguments=tc.function.arguments or ""
                    )
                )
                
        return NormalizedStreamChunk(
            content=content,
            tool_calls=tool_calls,
            raw_chunk=chunk
        )
