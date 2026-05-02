"""
Ollama Provider implementation with native and XML fallback protocols.
"""

import json
from typing import Any, AsyncGenerator, Dict, List, Optional

from loguru import logger
from ollama import AsyncClient

from ayder_cli.providers.base import (
    AIProvider,
    NormalizedStreamChunk,
    ToolCallDef,
)
from ayder_cli.providers.impl.ollama_drivers._errors import (
    OllamaServerToolBug,
    classify_ollama_error,
)
from ayder_cli.providers.impl.ollama_drivers.base import DriverMode
from ayder_cli.providers.impl.ollama_drivers.registry import DriverRegistry
from ayder_cli.providers.impl.ollama_inspector import OllamaInspector


class OllamaProvider(AIProvider):
    """
    Native provider for local Ollama models.
    Supports both native tool calling (chat_protocol = "ollama")
    and an XML-based prompt fallback (chat_protocol = "xml").

    Built on ollama.AsyncClient for full observability (timing, token counts).
    """

    def __init__(self, config: Any, interaction_sink: Any = None) -> None:
        super().__init__(config, interaction_sink)
        self.config = config
        host = getattr(config, "base_url", "http://localhost:11434")
        # Strip /v1 suffix if present (legacy config)
        if host.rstrip("/").endswith("/v1"):
            host = host.rstrip("/")[:-3]
        self._host = host
        self._client = AsyncClient(host=host)
        self._registry: DriverRegistry | None = None

    async def list_models(self) -> List[str]:
        try:
            response = await self._client.list()
            return [m.model for m in response.models if m.model]
        except Exception as e:
            logger.warning(f"Failed to list Ollama models: {e}")
            return []

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        options: Optional[Dict[str, Any]] = None,
        verbose: bool = False,
    ) -> NormalizedStreamChunk:
        # Collect full response from streaming
        final = NormalizedStreamChunk()
        async for chunk in self.stream_with_tools(messages, model, tools, options, verbose):
            final.content += chunk.content
            final.reasoning += chunk.reasoning
            if chunk.tool_calls:
                final.tool_calls = chunk.tool_calls
            if chunk.usage:
                final.usage = chunk.usage
        return final

    async def stream_with_tools(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        options: Optional[Dict[str, Any]] = None,
        verbose: bool = False,
    ) -> AsyncGenerator[NormalizedStreamChunk, None]:
        if self._registry is None:
            inspector = OllamaInspector(host=self._host)
            self._registry = DriverRegistry(inspector)

        driver_override_name = (
            None if self.config.chat_protocol == "ollama" else "generic_xml"
        )
        if (
            driver_override_name is not None
            and self.config.chat_protocol not in {"ollama", "xml"}
        ):
            logger.warning(
                f"Ollama chat_protocol={self.config.chat_protocol!r} is not "
                "recognized; forcing generic_xml fallback"
            )

        driver = await self._registry.resolve(model, override=driver_override_name)
        logger.debug(f"Ollama driver={driver.name} mode={driver.mode.value} for {model!r}")

        committed = False
        try:
            async for chunk in self._stream_with_driver(
                driver, messages, model, tools, options
            ):
                if chunk.content or chunk.reasoning or chunk.tool_calls:
                    committed = True
                yield chunk
        except OllamaServerToolBug as exc:
            if committed or not driver.fallback_driver:
                raise
            fallback = self._registry.get(driver.fallback_driver)
            logger.info(
                f"{driver.name} ({driver.mode.value}) failed mid-stream: {exc!r}; "
                f"transparently retrying with {fallback.name} ({fallback.mode.value})"
            )
            async for chunk in self._stream_with_driver(
                fallback, messages, model, tools, options
            ):
                yield chunk

    async def _stream_with_driver(
        self,
        driver: Any,
        messages: List[Dict[str, Any]],
        model: str,
        tools: Optional[List[Dict[str, Any]]],
        options: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[NormalizedStreamChunk, None]:
        try:
            if driver.mode is DriverMode.NATIVE:
                async for chunk in self._stream_native(messages, model, tools, options):
                    yield chunk
            else:
                async for chunk in self._stream_in_content(
                    driver, messages, model, tools, options
                ):
                    yield chunk
        except BaseException as exc:
            classified = classify_ollama_error(exc)
            if classified is exc:
                raise
            raise classified from exc

    async def _stream_native(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        tools: Optional[List[Dict[str, Any]]],
        options: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[NormalizedStreamChunk, None]:
        opts = options or {}
        num_ctx = opts.get("num_ctx", 65536)
        ollama_tools = self._convert_tools(tools) if tools else None
        ollama_messages = self._convert_messages(messages)

        stream = await self._client.chat(
            model=model,
            messages=ollama_messages,
            tools=ollama_tools,
            options={"num_ctx": num_ctx},
            keep_alive=-1,
            think=True,
            stream=True,
        )

        async for chunk in stream:
            msg = chunk.message
            usage = None
            if chunk.done:
                usage = {
                    "total_tokens": (chunk.prompt_eval_count or 0)
                    + (chunk.eval_count or 0),
                    "prompt_tokens": chunk.prompt_eval_count or 0,
                    "completion_tokens": chunk.eval_count or 0,
                    "prompt_eval_ns": chunk.prompt_eval_duration or 0,
                    "eval_ns": chunk.eval_duration or 0,
                    "load_ns": chunk.load_duration or 0,
                }

            tool_calls = []
            if msg.tool_calls:
                for i, tc in enumerate(msg.tool_calls):
                    args = tc.function.arguments
                    if isinstance(args, dict):
                        args = json.dumps(args)
                    tool_calls.append(
                        ToolCallDef(
                            id=f"call_{i}",
                            name=tc.function.name,
                            arguments=args,
                        )
                    )

            yield NormalizedStreamChunk(
                content=msg.content or "",
                reasoning=msg.thinking or "",
                tool_calls=tool_calls,
                raw_chunk=chunk,
                usage=usage,
            )

    async def _stream_in_content(
        self,
        driver: Any,
        messages: List[Dict[str, Any]],
        model: str,
        tools: Optional[List[Dict[str, Any]]],
        options: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[NormalizedStreamChunk, None]:
        opts = options or {}
        num_ctx = opts.get("num_ctx", 65536)
        formatted_messages = driver.render_tools_into_messages(messages, tools or [])
        ollama_messages = self._convert_messages(formatted_messages)

        stream = await self._client.chat(
            model=model,
            messages=ollama_messages,
            tools=None,
            options={"num_ctx": num_ctx},
            keep_alive=-1,
            think=True,
            stream=True,
        )

        raw_content = ""
        raw_thinking = ""
        display_filter = driver.display_filter()

        async for chunk in stream:
            msg = chunk.message
            content_text = msg.content or ""
            thinking_text = msg.thinking or ""
            raw_content += content_text
            raw_thinking += thinking_text

            usage = None
            if chunk.done:
                usage = {
                    "total_tokens": (chunk.prompt_eval_count or 0)
                    + (chunk.eval_count or 0),
                    "prompt_tokens": chunk.prompt_eval_count or 0,
                    "completion_tokens": chunk.eval_count or 0,
                    "prompt_eval_ns": chunk.prompt_eval_duration or 0,
                    "eval_ns": chunk.eval_duration or 0,
                    "load_ns": chunk.load_duration or 0,
                }

            if content_text or thinking_text or chunk.done:
                if display_filter is not None:
                    visible_content, visible_thinking = display_filter.feed(
                        content_text, thinking_text
                    )
                else:
                    visible_content = content_text
                    visible_thinking = thinking_text

                yield NormalizedStreamChunk(
                    content=visible_content,
                    reasoning=visible_thinking,
                    tool_calls=[],
                    raw_chunk=chunk,
                    usage=usage,
                )

        final_calls = driver.parse_tool_calls(raw_content, raw_thinking)
        if final_calls:
            yield NormalizedStreamChunk(tool_calls=final_calls)

    def _convert_messages(self, messages: List[Dict[str, Any]]) -> list:
        """Convert OpenAI-format messages to ollama SDK-compatible format.

        The ollama SDK's _copy_messages() runs each dict through:
            {k: v for k, v in dict(msg).items() if v}  → Message.model_validate()

        This means:
        - Falsy values (empty string, None, empty list) are DROPPED before validation
        - Message.tool_calls[].function.arguments must be dict, not JSON string
        - Tool result messages use 'tool_name' (not 'name')
        - Extra fields (tool_call_id, type, reasoning_content) are silently ignored
        """
        converted = []
        for msg in messages:
            role = msg["role"]
            content = msg.get("content") or None  # Normalize "" → None (SDK drops "" anyway)

            entry: Dict[str, Any] = {"role": role}

            # Only set content if non-empty (SDK drops falsy values anyway)
            if content:
                entry["content"] = content

            if role == "assistant" and msg.get("tool_calls"):
                tool_calls = []
                for tc in msg["tool_calls"]:
                    func = tc.get("function", {})
                    name = func.get("name", "").strip()

                    # Skip dummy/placeholder tool calls from streaming gaps
                    if not name:
                        continue

                    args = func.get("arguments", {})
                    # SDK requires arguments as dict (Mapping[str, Any]), not JSON string
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except (json.JSONDecodeError, ValueError):
                            logger.warning(
                                f"Malformed tool arguments for '{name}': "
                                f"{args!r:.200} — replacing with empty dict"
                            )
                            args = {}
                    if not isinstance(args, dict):
                        args = {}

                    tool_calls.append({
                        "function": {
                            "name": name,
                            "arguments": args,
                        }
                    })

                if tool_calls:
                    entry["tool_calls"] = tool_calls

            elif role == "tool":
                # SDK uses 'tool_name' not 'name' for tool result correlation
                tool_name = msg.get("name") or msg.get("tool_name") or ""
                if tool_name:
                    entry["tool_name"] = tool_name

            converted.append(entry)
        return converted

    def _convert_tools(self, tools: List[Dict[str, Any]]) -> list:
        """Convert OpenAI-format tool schemas to ollama format."""
        return tools
