"""
Ollama Provider implementation with native and XML fallback protocols.
"""

import json
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Dict, Iterator, List, Literal, Optional

from loguru import logger
from ollama import AsyncClient

from ayder_cli.parser import content_processor
from ayder_cli.providers.base import (
    AIProvider,
    NormalizedStreamChunk,
    ToolCallDef,
)

XML_INSTRUCTION = """
### TOOL PROTOCOL:
You MUST use the specialized XML format for all tool calls. Failure to use this format will result in a parsing error.
Format:
<tool_call>
<function=tool_name>
<parameter=key1>value1</parameter>
</function>
</tool_call>

Available tools:
{tool_schemas}

The system will execute your tool calls and return the results within `<tool_results>` tags. Do NOT generate `<tool_results>` yourself. Wait for the system to provide the result before taking your next action.

CRITICAL RULES:
1. DO NOT use these XML tags (like <function=> or <parameter=>) in your prose, descriptions, or summaries. Only use them when you intend to call a tool.
2. If you have completed the task and output "Perfect!", you MUST NOT include any tool calls in the same response. "Perfect!" signifies the absolute end of your activity for that task.
3. Use only one tool call at a time unless the task clearly requires parallel execution of independent tools.
"""

def inject_xml_prompt(messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Inject the XML_INSTRUCTION and tool schemas into the system prompt."""
    if not tools:
        return messages

    try:
        tool_schemas_str = json.dumps(tools, indent=2)
    except Exception as e:
        logger.warning(f"Failed to serialize tool schemas as JSON, using str(): {e}")
        tool_schemas_str = str(tools)

    instruction = XML_INSTRUCTION.format(tool_schemas=tool_schemas_str)

    formatted = list(messages)
    system_msg_idx = next((i for i, m in enumerate(formatted) if m.get("role") == "system"), None)

    if system_msg_idx is not None:
        new_msg = dict(formatted[system_msg_idx])
        new_msg["content"] = str(new_msg.get("content", "")) + "\n" + instruction
        formatted[system_msg_idx] = new_msg
    else:
        formatted.insert(0, {"role": "system", "content": instruction})

    return formatted


@dataclass
class StreamEvent:
    """Represents a discrete event emitted during streaming."""
    type: Literal["content", "think", "tool_start", "tool_args"]
    text: str = ""
    call_id: str = ""
    name: str = ""
    arguments: str = ""
    index: int = 0


class ToolStreamParser:
    """Parses raw LLM provider stream chunks into high-level events.

    Maintains a small buffer to reliably intercept and strip <think> and <tool_call>
    blocks from the text output, while yielding text and native tool call deltas
    in real-time.
    """

    def __init__(self):
        self._content_buffer = ""
        self._reasoning_buffer = ""
        self._tool_calls = {}

        self._state = "TEXT"
        self._chunk_buffer = ""

    def ingest(self, chunk: Any) -> Iterator[StreamEvent]:
        """Ingest a chunk from the LLM stream and yield parsed events."""
        if not hasattr(chunk, "choices") or not chunk.choices:
            return

        choice = chunk.choices[0]
        if not hasattr(choice, "delta"):
            return

        delta = choice.delta

        # 1. Process text content
        content = getattr(delta, "content", None)
        # OpenAI uses "reasoning_content", Ollama uses "reasoning"
        reasoning = getattr(delta, "reasoning_content", None) or getattr(delta, "reasoning", None)

        # Deepseek-v3.2 often puts its XML tool tags directly into the reasoning payload
        # instead of the content payload when using Ollama fallback.
        # So we must run BOTH through our _process_text state machine.

        if reasoning:
            # We process reasoning just like text to strip tags
            yield from self._process_text(reasoning, is_reasoning=True)

        if content:
            yield from self._process_text(content, is_reasoning=False)

        # 2. Process native tool calls
        tool_calls = getattr(delta, "tool_calls", None)
        if tool_calls:
            for tc in tool_calls:
                idx = getattr(tc, "index", 0)

                if idx not in self._tool_calls:
                    func = getattr(tc, "function", None)
                    name = getattr(func, "name", "") if func else ""
                    call_id = getattr(tc, "id", f"call_{idx}")
                    args = getattr(func, "arguments", "") if func else ""

                    self._tool_calls[idx] = {
                        "id": call_id,
                        "name": name,
                        "arguments": args,
                    }
                    if name:
                        yield StreamEvent(
                            type="tool_start", call_id=call_id, name=name, index=idx
                        )
                    if args:
                        yield StreamEvent(
                            type="tool_args",
                            call_id=call_id,
                            arguments=args,
                            index=idx,
                        )
                else:
                    func = getattr(tc, "function", None)
                    if func:
                        # Some providers might stream ID or name late
                        new_id = getattr(tc, "id", None)
                        if new_id and self._tool_calls[idx]["id"] != new_id:
                            self._tool_calls[idx]["id"] = new_id

                        new_name = getattr(func, "name", None)
                        if new_name and not self._tool_calls[idx]["name"]:
                            self._tool_calls[idx]["name"] = new_name
                            yield StreamEvent(
                                type="tool_start",
                                call_id=self._tool_calls[idx]["id"],
                                name=new_name,
                                index=idx,
                            )

                        new_args = getattr(func, "arguments", None)
                        if new_args:
                            self._tool_calls[idx]["arguments"] += new_args
                            yield StreamEvent(
                                type="tool_args",
                                call_id=self._tool_calls[idx]["id"],
                                arguments=new_args,
                                index=idx,
                            )

    def _process_text(self, text: str, is_reasoning: bool = False) -> Iterator[StreamEvent]:
        """State machine to filter out <think> and <tool_call> tags from stream."""
        self._chunk_buffer += text

        while self._chunk_buffer:
            if self._state == "TEXT":
                tag_idx = self._chunk_buffer.find("<")
                if tag_idx == -1:
                    safe_text = self._chunk_buffer
                    self._chunk_buffer = ""
                    if safe_text:
                        if is_reasoning:
                            self._reasoning_buffer += safe_text
                            yield StreamEvent(type="think", text=safe_text)
                        else:
                            self._content_buffer += safe_text
                            yield StreamEvent(type="content", text=safe_text)
                    break
                else:
                    if tag_idx > 0:
                        safe_text = self._chunk_buffer[:tag_idx]
                        self._chunk_buffer = self._chunk_buffer[tag_idx:]
                        if is_reasoning:
                            self._reasoning_buffer += safe_text
                            yield StreamEvent(type="think", text=safe_text)
                        else:
                            self._content_buffer += safe_text
                            yield StreamEvent(type="content", text=safe_text)

                    # We are at `<`. Determine if it's a known tag
                    lower_buf = self._chunk_buffer.lower()

                    # We need enough characters to match prefixes safely
                    max_tag_len = 21  # </minimax:tool_call>
                    if len(self._chunk_buffer) < max_tag_len:
                        if ">" not in self._chunk_buffer:
                            # Not closed yet, check if it COULD be a tag
                            if any(
                                tag.startswith(lower_buf)
                                for tag in [
                                    "<think>",
                                    "<tool_call>",
                                    "<function_calls>",
                                    "<minimax:tool_call>",
                                    "<function=",
                                    "</tool_call>",
                                    "</function_calls>",
                                    "</minimax:tool_call>",
                                    "</function>",
                                ]
                            ):
                                break  # Wait for more

                    # We have `<` and maybe `>`. See if it matches
                    if lower_buf.startswith("<think>"):
                        self._state = "IN_THINK"
                        self._chunk_buffer = self._chunk_buffer[7:]
                        continue

                    matched_tool = False
                    for tag in [
                        "<tool_call>",
                        "<function_calls>",
                        "<minimax:tool_call>",
                        "<function=",
                    ]:
                        if lower_buf.startswith(tag):
                            self._state = "IN_TOOL"
                            self._chunk_buffer = self._chunk_buffer[len(tag):]
                            matched_tool = True
                            break
                    if matched_tool:
                        continue

                    # Ignore orphaned closing tags in TEXT state
                    matched_orphan = False
                    for tag in [
                        "</tool_call>",
                        "</function_calls>",
                        "</minimax:tool_call>",
                        "</function>",
                    ]:
                        if lower_buf.startswith(tag):
                            self._chunk_buffer = self._chunk_buffer[len(tag):]
                            matched_orphan = True
                            break
                    if matched_orphan:
                        continue

                    # Not a tag we care about, emit `<`
                    if is_reasoning:
                        self._reasoning_buffer += "<"
                        yield StreamEvent(type="think", text="<")
                    else:
                        self._content_buffer += "<"
                        yield StreamEvent(type="content", text="<")
                    self._chunk_buffer = self._chunk_buffer[1:]

            elif self._state == "IN_THINK":
                close_idx = self._chunk_buffer.find("</think>")
                if close_idx == -1:
                    safe_len = len(self._chunk_buffer)
                    # Check for partial closing tag
                    for i in range(1, 9):
                        if self._chunk_buffer.endswith("</think>"[:i]):
                            safe_len -= i
                            break

                    if safe_len > 0:
                        safe_text = self._chunk_buffer[:safe_len]
                        self._chunk_buffer = self._chunk_buffer[safe_len:]
                        self._reasoning_buffer += safe_text
                        yield StreamEvent(type="think", text=safe_text)
                    break
                else:
                    safe_text = self._chunk_buffer[:close_idx]
                    if safe_text:
                        self._reasoning_buffer += safe_text
                        yield StreamEvent(type="think", text=safe_text)
                    self._state = "TEXT"
                    self._chunk_buffer = self._chunk_buffer[close_idx + 8:]
                    continue

            elif self._state == "IN_TOOL":
                # Suppress output during custom tool blocks
                lower_buf = self._chunk_buffer.lower()
                close_idx = lower_buf.find("</tool_call>")
                if close_idx != -1:
                    self._state = "TEXT"
                    self._chunk_buffer = self._chunk_buffer[close_idx + 12:]
                    continue

                close_idx2 = lower_buf.find("</function_calls>")
                if close_idx2 != -1:
                    self._state = "TEXT"
                    self._chunk_buffer = self._chunk_buffer[close_idx2 + 17:]
                    continue

                close_idx3 = lower_buf.find("</minimax:tool_call>")
                if close_idx3 != -1:
                    self._state = "TEXT"
                    self._chunk_buffer = self._chunk_buffer[close_idx3 + 20:]
                    continue

                close_idx4 = lower_buf.find("</function>")
                if close_idx4 != -1:
                    self._state = "TEXT"
                    self._chunk_buffer = self._chunk_buffer[close_idx4 + 11:]
                    continue

                # Wait for closing tag, but we can't buffer forever if the model forgot it.
                break

    def get_tool_calls(self) -> list[dict]:
        """Return the finalized list of standard tool calls."""
        res = []
        for idx in sorted(self._tool_calls.keys()):
            tc = self._tool_calls[idx]
            res.append(
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": tc["arguments"],
                    },
                }
            )
        return res

    def get_content(self) -> str:
        """Return the full unmodified text content."""
        return self._content_buffer

    def get_reasoning(self) -> str:
        """Return the accumulated reasoning content."""
        return self._reasoning_buffer


class XMLParserAdapter(ToolStreamParser):
    """Overrides ToolStreamParser to extract tools from text content rather than native streams."""
    def get_tool_calls(self) -> List[Dict[str, Any]]:
        # deepseek models sometimes put the XML into the reasoning payload instead of the content
        content = self.get_content()
        reasoning = self.get_reasoning()

        calls = []
        # Check both payloads, starting with content
        if content and content_processor.has_tool_calls(content):
            calls = content_processor.parse_tool_calls(content)
        elif reasoning and content_processor.has_tool_calls(reasoning):
            calls = content_processor.parse_tool_calls(reasoning)
        elif json_calls := content_processor.parse_json_tool_calls(content):
            calls = json_calls

        formatted = []
        for i, c in enumerate(calls):
            formatted.append({
                "id": f"call_{i}",
                "type": "function",
                "function": {
                    "name": c.get("name", "unknown"),
                    "arguments": json.dumps(c.get("arguments", {}))
                },
                "error": c.get("error")
            })
        return formatted


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
        self._client = AsyncClient(host=host)

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
        opts = options or {}
        num_ctx = opts.get("num_ctx", 65536)

        if self.config.chat_protocol != "ollama":
            logger.info(
                f"Ollama using XML fallback protocol (chat_protocol={self.config.chat_protocol!r})"
            )
            async for chunk in self._stream_xml_fallback(messages, model, tools, opts, verbose):
                yield chunk
            return

        # Native protocol path — direct ollama.AsyncClient
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

        async for chunk in stream:  # type: ignore[union-attr, attr-defined, assignment]
            msg = chunk.message  # type: ignore[union-attr, attr-defined]
            usage = None

            if chunk.done:  # type: ignore[union-attr, attr-defined]
                usage = {
                    "total_tokens": (chunk.prompt_eval_count or 0) + (chunk.eval_count or 0),  # type: ignore[union-attr, attr-defined]
                    "prompt_tokens": chunk.prompt_eval_count or 0,  # type: ignore[union-attr, attr-defined]
                    "completion_tokens": chunk.eval_count or 0,  # type: ignore[union-attr, attr-defined]
                    "prompt_eval_ns": chunk.prompt_eval_duration or 0,  # type: ignore[union-attr, attr-defined]
                    "eval_ns": chunk.eval_duration or 0,  # type: ignore[union-attr, attr-defined]
                    "load_ns": chunk.load_duration or 0,  # type: ignore[union-attr, attr-defined]
                }

            tool_calls = []
            if msg.tool_calls:
                for i, tc in enumerate(msg.tool_calls):
                    args = tc.function.arguments
                    if isinstance(args, dict):
                        args = json.dumps(args)
                    tool_calls.append(ToolCallDef(
                        id=f"call_{i}",
                        name=tc.function.name,
                        arguments=args,
                    ))

            yield NormalizedStreamChunk(
                content=msg.content or "",
                reasoning=msg.thinking or "",
                tool_calls=tool_calls,
                raw_chunk=chunk,
                usage=usage,
            )

    async def _stream_xml_fallback(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        tools: Optional[List[Dict[str, Any]]],
        opts: Dict[str, Any],
        verbose: bool,
    ) -> AsyncGenerator[NormalizedStreamChunk, None]:
        """XML fallback for models without native tool support."""
        formatted_messages = inject_xml_prompt(messages, tools or [])
        num_ctx = opts.get("num_ctx", 65536)
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

        parser = XMLParserAdapter()
        # Accumulate raw text to enable XML tool call extraction at the end.
        # _process_text strips XML from visible content, so we need the originals.
        raw_content_acc = ""
        raw_thinking_acc = ""

        async for chunk in stream:
            msg = chunk.message
            content_text = msg.content or ""
            thinking_text = msg.thinking or ""
            raw_content_acc += content_text
            raw_thinking_acc += thinking_text

            usage = None
            if chunk.done:
                usage = {
                    "total_tokens": (chunk.prompt_eval_count or 0) + (chunk.eval_count or 0),
                    "prompt_tokens": chunk.prompt_eval_count or 0,
                    "completion_tokens": chunk.eval_count or 0,
                    "prompt_eval_ns": chunk.prompt_eval_duration or 0,
                    "eval_ns": chunk.eval_duration or 0,
                    "load_ns": chunk.load_duration or 0,
                }

            # Emit a chunk when there is visible text, thinking, or we're done.
            # Prior behavior gated on content/thinking only — dropping usage on
            # empty-done chunks. That corrupted context-manager token accounting.
            # See opus47.md finding #5.
            if content_text or thinking_text or chunk.done:
                events: list[StreamEvent] = []
                if content_text:
                    events.extend(parser._process_text(content_text))
                if thinking_text:
                    events.extend(parser._process_text(thinking_text, is_reasoning=True))

                yield NormalizedStreamChunk(
                    content="".join(e.text for e in events if e.type == "content"),
                    reasoning="".join(e.text for e in events if e.type == "think"),
                    tool_calls=[],
                    raw_chunk=chunk,
                    usage=usage,
                )

        # Final yield for XML-parsed tool calls.
        # Inject raw accumulated text into parser buffers so get_tool_calls() can find XML.
        parser._content_buffer = raw_content_acc
        parser._reasoning_buffer = raw_thinking_acc
        final_calls = parser.get_tool_calls()
        if final_calls:
            yield NormalizedStreamChunk(
                tool_calls=[
                    ToolCallDef(
                        id=tc["id"],
                        name=tc["function"]["name"],
                        arguments=tc["function"]["arguments"],
                    ) for tc in final_calls
                ]
            )

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
