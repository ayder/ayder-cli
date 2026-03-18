"""
Ollama Provider implementation with native and XML fallback protocols.
"""

import json
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Dict, Iterator, List, Literal, Optional

import httpx
from loguru import logger

from ayder_cli.parser import content_processor
from ayder_cli.providers.base import (
    NormalizedStreamChunk,
    ToolCallDef,
)
from ayder_cli.providers.impl.openai import OpenAIProvider

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
    except Exception:
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


class OllamaProvider(OpenAIProvider):
    """
    Native provider for local Ollama models.
    Supports both native OpenAI tool calling (chat_protocol = "ollama")
    and an XML-based prompt fallback (chat_protocol = "xml").
    """

    MAX_TOKENS_PARAM = "max_tokens"
    # Ollama doesn't support OpenAI's stream_options parameter
    _STREAM_OPTIONS = False

    def _build_extra_body(self, options: Dict[str, Any]) -> Dict[str, Any] | None:
        """Pass Ollama-specific options via extra_body."""
        ollama_opts: Dict[str, Any] = {}
        if num_ctx := options.get("num_ctx"):
            ollama_opts["num_ctx"] = num_ctx
        return ollama_opts if ollama_opts else None

    async def list_models(self) -> List[str]:
        """
        List available models from the local Ollama instance.
        
        Uses Ollama's native /api/tags endpoint.
        """
        try:
            # Get base URL and strip '/v1' suffix to access native Ollama API
            base_url = getattr(self.config, "base_url", "http://localhost:11434")
            # Remove /v1 suffix if present to get native Ollama API endpoint
            ollama_base = base_url.rstrip("/")
            if ollama_base.endswith("/v1"):
                ollama_base = ollama_base[:-3]
            
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{ollama_base}/api/tags", timeout=10.0)
                response.raise_for_status()
                data = response.json()
                
                # Extract model names from the response
                models = data.get("models", [])
                return [m.get("name", "") for m in models if m.get("name")]
                
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
        if self.config.chat_protocol == "ollama":
            return await super().chat(messages, model, tools, options, verbose)

        # Fallback XML logic
        formatted_messages = inject_xml_prompt(messages, tools or [])
        response = await super().chat(
            messages=formatted_messages,
            model=model,
            tools=None, # Disable native tools for XML protocol
            options=options,
            verbose=verbose,
        )
        
        # Parse XML from the final content or reasoning
        calls = []
        content = response.content
        reasoning = response.reasoning
        
        if content and content_processor.has_tool_calls(content):
            calls = content_processor.parse_tool_calls(content)
        elif reasoning and content_processor.has_tool_calls(reasoning):
            calls = content_processor.parse_tool_calls(reasoning)
        elif json_calls := content_processor.parse_json_tool_calls(content):
            calls = json_calls

        tool_calls = [
            ToolCallDef(
                id=tc["id"],
                name=tc["function"]["name"],
                arguments=tc["function"]["arguments"]
            ) for tc in calls
        ]
        
        # Strip XML from content for final normalized response
        clean_content = content_processor.strip_for_display(content)
        
        return NormalizedStreamChunk(
            content=clean_content,
            reasoning=response.reasoning,
            tool_calls=tool_calls,
            raw_chunk=response.raw_chunk,
            usage=response.usage
        )

    async def stream_with_tools(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        options: Optional[Dict[str, Any]] = None,
        verbose: bool = False,
    ) -> AsyncGenerator[NormalizedStreamChunk, None]:

        if self.config.chat_protocol == "ollama":
            # Use ToolStreamParser to handle <think> tags that Ollama models
            # (e.g. qwen3, deepseek) embed in the content field
            parser = ToolStreamParser()
            async for chunk in super().stream_with_tools(messages, model, tools, options, verbose):
                # If the base provider already extracted reasoning_content natively, pass through
                if chunk.reasoning or chunk.tool_calls:
                    yield chunk
                    continue

                # Otherwise, run content through parser to extract <think> blocks
                if chunk.content and chunk.raw_chunk:
                    events = list(parser.ingest(chunk.raw_chunk))
                    content_text = "".join(e.text for e in events if e.type == "content")
                    reasoning_text = "".join(e.text for e in events if e.type == "think")
                    yield NormalizedStreamChunk(
                        content=content_text,
                        reasoning=reasoning_text,
                        tool_calls=chunk.tool_calls,
                        raw_chunk=chunk.raw_chunk,
                        usage=chunk.usage,
                    )
                else:
                    yield chunk
            return

        # Fallback XML logic for streaming
        formatted_messages = inject_xml_prompt(messages, tools or [])
        
        # Call the base provider WITHOUT tools (forcing text output)
        async_stream = super().stream_with_tools(
            messages=formatted_messages,
            model=model,
            tools=None, 
            options=options,
            verbose=verbose,
        )

        parser = XMLParserAdapter()

        async for base_chunk in async_stream:
            # Pass the raw chunk (which is now just text) through our filter
            events = list(parser.ingest(base_chunk.raw_chunk))
            
            yield NormalizedStreamChunk(
                content="".join(e.text for e in events if e.type == "content"),
                reasoning="".join(e.text for e in events if e.type == "think"),
                tool_calls=[], 
                raw_chunk=base_chunk.raw_chunk,
                usage=base_chunk.usage
            )

        # Final yield for tool calls
        final_calls = parser.get_tool_calls()
        if final_calls:
            yield NormalizedStreamChunk(
                tool_calls=[
                    ToolCallDef(
                        id=tc["id"],
                        name=tc["function"]["name"],
                        arguments=tc["function"]["arguments"]
                    ) for tc in final_calls
                ]
            )
