"""
Gemini Provider implementation using google-genai.
"""

import base64
import json
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional

from ayder_cli.core.config import Config
from ayder_cli.log import get_logger
from ayder_cli.providers.base import (
    AIProvider,
    NormalizedStreamChunk,
    ToolCallDef,
)

logger = get_logger("llm")

# Keywords a Gemini function declaration's ``parameters`` Schema accepts, in the
# JSON-Schema spelling ayder's tool definitions use. This is google-genai 3.3.0's
# ``types.Schema`` field set minus ``additional_properties`` (the Gemini API rejects
# it: 400 "Unknown name 'additional_properties'") and ``defs``/``ref`` (the SDK cannot
# take them from ``$defs``/``$ref``). Anything else is dropped.
_GEMINI_SCHEMA_KEYS = frozenset({
    "type", "format", "title", "description", "nullable", "enum", "default",
    "example", "items", "properties", "required", "propertyOrdering", "anyOf",
    "minItems", "maxItems", "minLength", "maxLength", "minProperties",
    "maxProperties", "minimum", "maximum", "pattern",
})


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
        except Exception:
            logger.exception("Gemini chat failed")
            raise

    def _normalize_response(self, response: Any) -> NormalizedStreamChunk:
        """Map Gemini response to normalized format."""
        content = ""
        tool_calls = []
        
        if not response.candidates:
            return NormalizedStreamChunk(raw_chunk=response)
            
        for part in response.candidates[0].content.parts or []:
            if part.text:
                content += part.text
            elif part.function_call:
                tool_calls.append(self._function_call_def(part.function_call, part.thought_signature))


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
            logger.debug("Gemini Stream Request: model={}, tools={}", model, len(tools) if tools else 0)
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
                    logger.trace("Gemini Chunk Received")
                yield self._normalize_chunk(chunk)
                
        except Exception:
            logger.exception("Gemini streaming failed")
            raise

    def _normalize_chunk(self, chunk: Any) -> NormalizedStreamChunk:
        """Map Gemini stream chunk to normalized format."""
        content = ""
        tool_calls = []
        usage = None

        if not chunk.candidates:
            return NormalizedStreamChunk(raw_chunk=chunk)

        candidate_content = chunk.candidates[0].content
        parts = (candidate_content.parts if candidate_content else None) or []
        for part in parts:
            if part.text:
                content += part.text
            elif part.function_call:
                # Gemini emits complete function calls, not deltas
                tool_calls.append(self._function_call_def(part.function_call, part.thought_signature))

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
    def _function_call_def(fc: Any, thought_signature: Optional[bytes] = None) -> ToolCallDef:
        """Normalize one SDK ``FunctionCall``.

        ``args`` is a plain dict in google-genai. The id is the SDK's own call id
        when present, else a generated one: the tool name alone would merge two
        calls to the same tool in the chat loop's id match. Results map back by
        tool name in ``_convert_messages``, so a generated id is safe.

        ``thought_signature`` is ``Part.thought_signature`` (bytes): it lives on the
        Part, not on the FunctionCall. It is stored base64-encoded so the history
        stays JSON; the SDK decodes the text back to the same bytes when the Part is
        rebuilt for the next request.
        """
        call_id = getattr(fc, "id", None) or f"{fc.name}_{uuid.uuid4().hex[:8]}"
        return ToolCallDef(
            id=call_id,
            name=fc.name,
            arguments=json.dumps(dict(fc.args or {})),
            thought_signature=(
                base64.b64encode(thought_signature).decode("ascii")
                if thought_signature
                else None
            ),
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
                    part: Dict[str, Any] = {
                        "function_call": {
                            "name": tc["function"]["name"],
                            "args": args
                        }
                    }
                    if tc.get("thought_signature"):
                        part["thought_signature"] = tc["thought_signature"]
                    parts.append(part)
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
    def _gemini_schema(schema: Any) -> Any:
        """Keep only the JSON-Schema keywords Gemini function declarations accept.

        Recurses into ``properties`` (a name -> schema map: every property NAME is
        kept), ``items`` and ``anyOf``. ``oneOf`` is sent as ``anyOf`` (Gemini has no
        oneOf). A JSON-Schema type list such as ["string", "null"] becomes type
        "string" with nullable true.
        """
        if not isinstance(schema, dict):
            return schema
        out: Dict[str, Any] = {}
        for key, value in schema.items():
            if key == "oneOf" and "anyOf" not in schema:
                key = "anyOf"
            if key not in _GEMINI_SCHEMA_KEYS:
                continue
            if key == "properties" and isinstance(value, dict):
                out[key] = {
                    name: GeminiProvider._gemini_schema(sub) for name, sub in value.items()
                }
            elif key == "items":
                out[key] = GeminiProvider._gemini_schema(value)
            elif key == "anyOf" and isinstance(value, list):
                out[key] = [GeminiProvider._gemini_schema(sub) for sub in value]
            elif key == "type" and isinstance(value, list):
                concrete = [t for t in value if t != "null"]
                if concrete:
                    out["type"] = concrete[0]
                if "null" in value:
                    out["nullable"] = True
            else:
                out[key] = value
        return out

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
                    "parameters": GeminiProvider._gemini_schema(
                        func.get("parameters", {"type": "object", "properties": {}})
                    )
                }]
            })
        return gemini_tools
