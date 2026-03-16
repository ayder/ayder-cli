"""
Gemini Provider implementation using google-genai.
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

class GeminiProvider(AIProvider):
    """Provider for Google Gemini models."""

    def __init__(self, config: Config, interaction_sink=None):
        self.config = config
        self.interaction_sink = interaction_sink
        from google import genai
        self.client = genai.Client(api_key=config.api_key)

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        options: Optional[Dict[str, Any]] = None,
        verbose: bool = False,
    ) -> NormalizedStreamChunk:
        system_prompt, gemini_messages = self._convert_messages(messages)
        
        from google.genai.types import GenerateContentConfig
        gen_config = GenerateContentConfig()
        if system_prompt:
            gen_config.system_instruction = system_prompt
        if tools:
            gen_config.tools = self._convert_tools(tools)  # type: ignore[assignment]

        try:
            response = await self.client.aio.models.generate_content(
                model=model,
                contents=gemini_messages,
                config=gen_config,
            )
            return self._normalize_response(response)
        except Exception as e:
            logger.error(f"Gemini chat failed: {e}")
            raise

    def _normalize_response(self, response: Any) -> NormalizedStreamChunk:
        """Map Gemini response to normalized format."""
        content = ""
        tool_calls = []
        
        if not response.candidates:
            return NormalizedStreamChunk(raw_chunk=response)
            
        for part in response.candidates[0].content.parts:
            if part.text:
                content += part.text
            elif part.function_call:
                args_dict = type(part.function_call.args).to_dict(part.function_call.args)
                tool_calls.append(
                    ToolCallDef(
                        id=part.function_call.name,
                        name=part.function_call.name,
                        arguments=json.dumps(args_dict)
                    )
                )
                
        usage = {"total_tokens": getattr(response.usage_metadata, "total_token_count", 0)}
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
        
        system_prompt, gemini_messages = self._convert_messages(messages)
        
        # Build configuration object
        from google.genai.types import GenerateContentConfig
        
        gen_config = GenerateContentConfig()
        if system_prompt:
            gen_config.system_instruction = system_prompt
            
        if tools:
            gen_config.tools = self._convert_tools(tools)  # type: ignore[assignment]

        if options and getattr(self.config, "max_output_tokens", None):
            gen_config.max_output_tokens = self.config.max_output_tokens

        if verbose:
            logger.debug(f"Gemini Stream Request: model={model}, tools={len(tools) if tools else 0}")
            if self.interaction_sink:
                self.interaction_sink.on_llm_request_debug(messages, model, tools, options)

        try:
            async_stream = await self.client.aio.models.generate_content_stream(
                model=model,
                contents=gemini_messages,
                config=gen_config,
            )
            
            async for chunk in async_stream:
                if verbose:
                    logger.debug("Gemini Chunk Received")
                yield self._normalize_chunk(chunk)
                
        except Exception as e:
            logger.error(f"Gemini streaming failed: {e}")
            raise

    def _normalize_chunk(self, chunk: Any) -> NormalizedStreamChunk:
        """Map Gemini stream chunk to normalized format."""
        content = ""
        tool_calls = []
        usage = None

        if not chunk.candidates:
            return NormalizedStreamChunk(raw_chunk=chunk)

        part = chunk.candidates[0].content.parts[0] if chunk.candidates[0].content.parts else None
        
        if part:
            if part.text:
                content = part.text
            elif part.function_call:
                # Gemini emits complete function calls, not deltas
                args_dict = type(part.function_call.args).to_dict(part.function_call.args)
                tool_calls.append(
                    ToolCallDef(
                        id=part.function_call.name,  # Gemini doesn't use unique IDs per call
                        name=part.function_call.name,
                        arguments=json.dumps(args_dict)
                    )
                )

        # Usage info is often attached to the final chunk
        if hasattr(chunk, "usage_metadata") and chunk.usage_metadata:
            usage = {
                "total_tokens": getattr(chunk.usage_metadata, "total_token_count", 0)
            }

        return NormalizedStreamChunk(
            content=content,
            tool_calls=tool_calls,
            raw_chunk=chunk,
            usage=usage
        )

    @staticmethod
    def _convert_messages(messages: List[Dict[str, Any]]) -> tuple[str, List[Dict[str, Any]]]:
        """Extract system prompt and convert messages to Gemini's format."""
        system_prompt = ""
        gemini_messages = []
        
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "") or ""
            tool_calls_raw = msg.get("tool_calls")

            if role == "system":
                system_prompt += content + "\n"
                continue

            # Gemini uses "user" and "model"
            gemini_role = "model" if role == "assistant" else "user"
            
            parts = []
            if content:
                parts.append({"text": content})
                
            if tool_calls_raw:
                # Format previous function calls generated by the model
                for tc in tool_calls_raw:
                    args = tc["function"]["arguments"]
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except json.JSONDecodeError:
                            args = {}
                    parts.append({
                        "function_call": {
                            "name": tc["function"]["name"],
                            "args": args
                        }
                    })
            elif role == "tool":
                # Tool result returned by user
                tool_name = msg.get("name", "unknown")
                # Gemini requires function responses to be structured
                parts.append({
                    "function_response": {
                        "name": tool_name,
                        "response": {"result": content}
                    }
                })

            if parts:
                gemini_messages.append({"role": gemini_role, "parts": parts})

        return system_prompt.strip(), gemini_messages

    @staticmethod
    def _convert_tools(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert OpenAI schema to Gemini schema."""
        gemini_tools = []
        for tool in tools:
            func = tool.get("function", {})
            gemini_tools.append({
                "function_declarations": [{
                    "name": func.get("name"),
                    "description": func.get("description", ""),
                    "parameters": func.get("parameters", {"type": "object", "properties": {}})
                }]
            })
        return gemini_tools
