"""
Claude Provider implementation using AsyncAnthropic.
"""

import json
from typing import Any, AsyncGenerator, Dict, List, Optional
from loguru import logger

from ayder_cli.core.config import Config
from ayder_cli.providers.base import (
    AIProvider,
    NormalizedStreamChunk,
    ToolCallDef,
)


class ClaudeProvider(AIProvider):
    """Provider for Anthropic Claude models."""

    def __init__(self, config: Config, interaction_sink=None):
        self.config = config
        self.interaction_sink = interaction_sink
        # Lazy import
        from anthropic import AsyncAnthropic
        self.client = AsyncAnthropic(api_key=config.api_key)

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        options: Optional[Dict[str, Any]] = None,
        verbose: bool = False,
    ) -> NormalizedStreamChunk:
        system_prompt, anthropic_messages = self._convert_messages(messages)
        
        kwargs: Dict[str, Any] = {
            "model": model,
            "messages": anthropic_messages,
            "max_tokens": getattr(self.config, "max_output_tokens", 4096),
            "stream": False,
        }
        if system_prompt:
            kwargs["system"] = system_prompt
        if tools:
            kwargs["tools"] = self._convert_tools(tools)
            
        try:
            response = await self.client.messages.create(**kwargs)
            return self._normalize_response(response)
        except Exception as e:
            logger.error(f"Claude chat failed: {e}")
            raise

    def _normalize_response(self, response: Any) -> NormalizedStreamChunk:
        """Map Anthropic Message response to normalized format."""
        content = ""
        tool_calls = []
        
        for block in response.content:
            if block.type == "text":
                content += block.text
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolCallDef(
                        id=block.id,
                        name=block.name,
                        arguments=json.dumps(block.input)
                    )
                )
        
        usage = {"total_tokens": response.usage.output_tokens + response.usage.input_tokens}
        return NormalizedStreamChunk(
            content=content,
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
        
        system_prompt, anthropic_messages = self._convert_messages(messages)
        
        kwargs: Dict[str, Any] = {
            "model": model,
            "messages": anthropic_messages,
            "max_tokens": getattr(self.config, "max_output_tokens", 4096),
        }
        if system_prompt:
            kwargs["system"] = system_prompt
            
        if tools:
            kwargs["tools"] = self._convert_tools(tools)
            
        if options and (stop := options.get("stop_sequences")):
            kwargs["stop_sequences"] = stop

        if verbose:
            logger.debug(f"Claude Stream Request: model={model}, tools={len(tools) if tools else 0}")
            if self.interaction_sink:
                self.interaction_sink.on_llm_request_debug(messages, model, tools, options)

        try:
            async with self.client.messages.stream(**kwargs) as stream:
                async for chunk in stream:
                    if verbose:
                        logger.debug(f"Claude Chunk: type={chunk.type}")
                    yield self._normalize_chunk(chunk)
        except Exception as e:
            logger.error(f"Claude streaming failed: {e}")
            raise

    def _normalize_chunk(self, chunk: Any) -> NormalizedStreamChunk:
        """Map Anthropic stream events to our normalized format."""
        content = ""
        tool_calls = []
        usage = None

        if chunk.type == "content_block_delta":
            if chunk.delta.type == "text_delta":
                content = chunk.delta.text
            elif chunk.delta.type == "input_json_delta":
                # Anthropic sends tool arguments as a continuous JSON string delta
                tool_calls.append(
                    ToolCallDef(id="", name="", arguments=chunk.delta.partial_json)
                )
                
        elif chunk.type == "content_block_start":
            if chunk.content_block.type == "tool_use":
                # Start of a new tool call. We grab the ID and Name here.
                tool_calls.append(
                    ToolCallDef(
                        id=chunk.content_block.id,
                        name=chunk.content_block.name,
                        arguments=""
                    )
                )
                
        elif chunk.type == "message_delta":
            if hasattr(chunk, "usage") and chunk.usage:
                usage = {
                    "total_tokens": getattr(chunk.usage, "output_tokens", 0)
                }

        return NormalizedStreamChunk(
            content=content,
            tool_calls=tool_calls,
            raw_chunk=chunk,
            usage=usage
        )

    @staticmethod
    def _convert_messages(messages: List[Dict[str, Any]]) -> tuple[str, List[Dict[str, Any]]]:
        """Extract system prompt and format messages for Anthropic."""
        system_prompt = ""
        anthropic_messages = []
        
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "") or ""
            tool_calls_raw = msg.get("tool_calls")
            
            if role == "system":
                system_prompt += content + "\n"
                continue
                
            # Handle tool calls (Anthropic expects them in the content array)
            if tool_calls_raw:
                content_blocks = []
                if content:
                    content_blocks.append({"type": "text", "text": content})
                for tc in tool_calls_raw:
                    args = tc["function"]["arguments"]
                    import json
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except json.JSONDecodeError:
                            args = {}
                    content_blocks.append({
                        "type": "tool_use",
                        "id": tc["id"],
                        "name": tc["function"]["name"],
                        "input": args,
                    })
                anthropic_messages.append({"role": "assistant", "content": content_blocks})
            elif role == "tool":
                # Anthropic expects tool results wrapped in a 'user' message
                tool_id = msg.get("tool_call_id", "")
                anthropic_messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "content": content,
                    }]
                })
            else:
                anthropic_messages.append({"role": role, "content": content})
                
        return system_prompt.strip(), anthropic_messages

    @staticmethod
    def _convert_tools(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert OpenAI tool schema to Anthropic tool schema."""
        anthropic_tools = []
        for tool in tools:
            func = tool.get("function", {})
            anthropic_tools.append({
                "name": func.get("name"),
                "description": func.get("description", ""),
                "input_schema": func.get("parameters", {"type": "object", "properties": {}}),
            })
        return anthropic_tools
