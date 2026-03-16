"""
Qwen Native Provider implementation using DashScope SDK.
"""

import os
from typing import Any, AsyncGenerator, Dict, List, Optional
from loguru import logger

from ayder_cli.core.config import Config
from ayder_cli.providers.base import (
    AIProvider,
    NormalizedStreamChunk,
    ToolCallDef,
)


class QwenNativeProvider(AIProvider):
    """
    Provider for Alibaba Qwen models using the official DashScope SDK.
    Optimized for Qwen's specific ReAct tool-calling and reasoning patterns.
    """

    def __init__(self, config: Config, interaction_sink=None):
        self.config = config
        self.interaction_sink = interaction_sink
        # DashScope often uses an environment variable or explicit key
        self.api_key = config.api_key or os.environ.get("DASHSCOPE_API_KEY")

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        options: Optional[Dict[str, Any]] = None,
        verbose: bool = False,
    ) -> NormalizedStreamChunk:
        # Lazy import DashScope
        from dashscope import Generation
        
        # Qwen prefers 'result_format="message"' for tool calling
        response = Generation.call(
            model=model,
            api_key=self.api_key,
            messages=messages,
            tools=tools,
            result_format='message'
        )
        
        if response.status_code != 200:
            raise RuntimeError(f"Qwen API failed: {response.message}")
            
        return self._normalize_response(response)

    async def stream_with_tools(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        options: Optional[Dict[str, Any]] = None,
        verbose: bool = False,
    ) -> AsyncGenerator[NormalizedStreamChunk, None]:
        from dashscope import Generation
        
        responses = Generation.call(
            model=model,
            api_key=self.api_key,
            messages=messages,
            tools=tools,
            result_format='message',
            stream=True,
            incremental_output=True # Qwen specific streaming
        )

        for response in responses:
            if response.status_code != 200:
                logger.error(f"Qwen streaming error: {response.message}")
                break
            yield self._normalize_chunk(response)

    def _normalize_response(self, response: Any) -> NormalizedStreamChunk:
        msg = response.output.choices[0].message
        content = msg.get("content", "") or ""
        tool_calls = []
        
        raw_calls = msg.get("tool_calls", [])
        if raw_calls:
            for tc in raw_calls:
                tool_calls.append(
                    ToolCallDef(
                        id=tc.get("id", ""),
                        name=tc["function"]["name"],
                        arguments=tc["function"]["arguments"]
                    )
                )
        
        return NormalizedStreamChunk(
            content=content,
            tool_calls=tool_calls,
            raw_chunk=response
        )

    def _normalize_chunk(self, response: Any) -> NormalizedStreamChunk:
        # DashScope incremental output sends the delta in the message
        msg = response.output.choices[0].message
        content = msg.get("content", "") or ""
        tool_calls = []
        
        raw_calls = msg.get("tool_calls", [])
        if raw_calls:
            for tc in raw_calls:
                tool_calls.append(
                    ToolCallDef(
                        id=tc.get("id", ""),
                        name=tc["function"].get("name", ""),
                        arguments=tc["function"].get("arguments", "")
                    )
                )
                
        return NormalizedStreamChunk(
            content=content,
            tool_calls=tool_calls,
            raw_chunk=response
        )
