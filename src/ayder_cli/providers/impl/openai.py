"""
OpenAI Provider implementation.
"""

from typing import Any, AsyncGenerator, Dict, List, Optional
from loguru import logger
from openai import AsyncOpenAI

from ayder_cli.core.config import Config
from ayder_cli.providers.base import (
    AIProvider,
    NormalizedStreamChunk,
    ToolCallDef,
)


class OpenAIProvider(AIProvider):
    """Provider for OpenAI-compatible APIs."""

    # OpenAI API uses max_completion_tokens for all current models.
    # Subclasses for OpenAI-compatible APIs (Ollama, DeepSeek, …) that
    # still expect the legacy name can override this to "max_tokens".
    MAX_TOKENS_PARAM = "max_completion_tokens"

    def __init__(self, config: Config, interaction_sink=None):
        self.config = config
        self.interaction_sink = interaction_sink
        self.client = AsyncOpenAI(
            base_url=config.base_url,
            api_key=config.api_key,
        )

    async def list_models(self) -> List[str]:
        """
        List available models from the OpenAI-compatible API.
        
        Returns empty list if the API doesn't support model listing.
        """
        try:
            response = await self.client.models.list()
            # Extract model IDs from the response
            return [model.id for model in response.data if hasattr(model, "id")]
        except Exception as e:
            logger.warning(f"Failed to list models: {e}")
            return []

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        options: Optional[Dict[str, Any]] = None,
        verbose: bool = False,
    ) -> NormalizedStreamChunk:
        kwargs: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
        }
        if tools:
            kwargs["tools"] = tools
        if options:
            if stop := options.get("stop_sequences"):
                kwargs["stop"] = stop
            if max_tokens := options.get("max_output_tokens"):
                kwargs[self.MAX_TOKENS_PARAM] = max_tokens

        if verbose:
            logger.debug(f"OpenAI Chat Request: model={model}, tools={len(tools) if tools else 0}")
            if self.interaction_sink:
                self.interaction_sink.on_llm_request_debug(messages, model, tools, options)

        try:
            response = await self.client.chat.completions.create(**kwargs)
            return self._normalize_response(response)
        except Exception as e:
            logger.error(f"OpenAI chat failed: {e}")
            raise

    def _normalize_response(self, response: Any) -> NormalizedStreamChunk:
        """Map full OpenAI response object to normalized format."""
        msg = response.choices[0].message
        content = msg.content or ""
        reasoning = getattr(msg, "reasoning_content", "") or ""
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
            reasoning=reasoning,
            tool_calls=tool_calls,
            raw_chunk=response,
            usage=usage
        )

    async def stream_with_tools(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        options: Optional[Dict[str, Any]] = None,
        verbose: bool = False,
    ) -> AsyncGenerator[NormalizedStreamChunk, None]:
        
        kwargs: Dict[str, Any] = {
            "model": model,
            "messages": messages, # OpenAI handles the standard format natively
            "stream": True,
            "stream_options": {"include_usage": True},
        }

        if tools:
            kwargs["tools"] = tools

        if options:
            if stop := options.get("stop_sequences"):
                kwargs["stop"] = stop
            if max_tokens := options.get("max_output_tokens"):
                kwargs[self.MAX_TOKENS_PARAM] = max_tokens

        if verbose:
            logger.debug(f"OpenAI Stream Request: model={model}, tools={len(tools) if tools else 0}")
            if self.interaction_sink:
                self.interaction_sink.on_llm_request_debug(messages, model, tools, options)

        try:
            async_stream = await self.client.chat.completions.create(**kwargs)
            
            async for chunk in async_stream:
                if verbose:
                    delta = chunk.choices[0].delta if chunk.choices else None
                    c = getattr(delta, "content", "") if delta else ""
                    rc = getattr(delta, "reasoning_content", "") if delta else ""
                    tc = getattr(delta, "tool_calls", []) if delta else []
                    logger.debug(
                        f"OpenAI Chunk: content_len={len(c or '')}, "
                        f"reasoning_len={len(rc or '')}, tools={len(tc or [])}"
                    )

                yield self._normalize_chunk(chunk)
                
        except Exception as e:
            logger.error(f"OpenAI streaming failed: {e}")
            raise

    def _normalize_chunk(self, chunk: Any) -> NormalizedStreamChunk:
        """Map the OpenAI chunk object directly to our normalized format.
        
        Handles both complete tool calls (non-streaming) and partial tool call deltas (streaming).
        """
        content = ""
        reasoning = ""
        tool_calls = []
        usage = None

        if hasattr(chunk, "usage") and chunk.usage:
            # Map usage dict safely
            usage = {
                "total_tokens": getattr(chunk.usage, "total_tokens", 0) or 0
            }

        if not chunk.choices:
            return NormalizedStreamChunk(raw_chunk=chunk, usage=usage)

        delta = chunk.choices[0].delta
        if not delta:
            return NormalizedStreamChunk(raw_chunk=chunk, usage=usage)

        content = getattr(delta, "content", "") or ""
        reasoning = getattr(delta, "reasoning_content", "") or ""

        if delta.tool_calls:
            for tc in delta.tool_calls:
                # Streaming deltas include 'index' to identify which tool call is being built
                call_index = getattr(tc, "index", 0)
                call_id = getattr(tc, "id", "") or ""
                
                func = getattr(tc, "function", None)
                if func:
                    name = getattr(func, "name", "") or ""
                    args = getattr(func, "arguments", "") or ""
                    
                    # We pass the index back as an ID if none is provided yet,
                    # so the ChatLoop buffer can stitch streaming arguments together
                    tool_calls.append(
                        ToolCallDef(
                            id=call_id or f"idx_{call_index}", 
                            name=name, 
                            arguments=args,
                        )
                    )
                    # We dynamically patch the index onto the definition object for the accumulator
                    setattr(tool_calls[-1], "_stream_index", call_index)

        return NormalizedStreamChunk(
            content=content,
            reasoning=reasoning,
            tool_calls=tool_calls,
            raw_chunk=chunk,
            usage=usage
        )
