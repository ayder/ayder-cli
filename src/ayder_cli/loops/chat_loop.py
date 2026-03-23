"""
ChatLoop — async chat loop for LLM agent interactions.

Extracts all LLM call + tool execution logic into a testable,
widget-free class. Communication with UI happens exclusively
through the ChatCallbacks protocol.

Renamed from TuiChatLoop (originally in tui/chat_loop.py) to enable
reuse by agents and other consumers beyond the TUI.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, List, Protocol, runtime_checkable

from ayder_cli.application.execution_policy import ExecutionPolicy, ToolRequest
from ayder_cli.core.context_manager import ContextManager, truncate_tool_result
from ayder_cli.providers.base import _FunctionCall, _ToolCall

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ayder_cli.providers import AIProvider
    from ayder_cli.tools.registry import ToolRegistry


@dataclass
class ChatLoopConfig:
    """Configuration for the chat loop."""

    model: str = "qwen3-coder:latest"
    provider: str = "ollama"  # Needed for provider initialization
    num_ctx: int = 65536
    max_output_tokens: int = 4096
    stop_sequences: list = field(default_factory=list)
    permissions: set = field(default_factory=lambda: {"r"})
    tool_tags: frozenset | None = field(
        default_factory=lambda: frozenset({"core", "metadata"})
    )
    max_history: int = 0
    verbose: bool = False
    pre_iteration_hook: Any | None = None  # async callable(messages) -> None


@runtime_checkable
class ChatCallbacks(Protocol):
    """Protocol so ChatLoop never touches UI widgets directly."""

    def on_thinking_start(self) -> None: ...
    def on_thinking_stop(self) -> None: ...
    def on_assistant_content(self, text: str) -> None: ...
    def on_thinking_content(self, text: str) -> None: ...
    def on_token_usage(self, total_tokens: int) -> None: ...

    def on_tool_start(self, call_id: str, name: str, arguments: dict) -> None: ...
    def on_tool_complete(self, call_id: str, result: str) -> None: ...
    def on_tools_cleanup(self) -> None: ...
    def on_system_message(self, text: str) -> None: ...
    async def request_confirmation(
        self, name: str, arguments: dict
    ) -> object | None: ...
    def is_cancelled(self) -> bool: ...


class ChatLoop:
    """Async chat loop that drives LLM agent interactions.

    Does NOT own any UI widgets.
    """

    def __init__(
        self,
        llm: AIProvider,
        registry: ToolRegistry,
        messages: list[dict],
        config: ChatLoopConfig,
        callbacks: ChatCallbacks,
        context_manager=None,  # Optional — backward compat for tests
    ) -> None:
        self.llm = llm
        self.registry = registry
        self.messages = messages
        self.config = config
        self.cb = callbacks
        self._total_tokens = 0
        if context_manager is not None:
            self.context_manager = context_manager
        else:
            # Backward compat: create one from ChatLoopConfig (legacy path)
            self.context_manager = ContextManager(config=config, model=config.model)

    # -- public API ----------------------------------------------------------

    @property
    def total_tokens(self) -> int:
        return self._total_tokens

    async def run(self, *, no_tools: bool = False) -> None:
        """Main loop: call LLM, handle tools, repeat until text-only or cancel."""
        # Lazy init: detect real context length for Ollama models
        if hasattr(self.context_manager, "detect_context_length"):
            await self.context_manager.detect_context_length()

        while True:
            if self.cb.is_cancelled():
                return

            # Pre-iteration hook (used for agent summary injection)
            if self.config.pre_iteration_hook is not None:
                await self.config.pre_iteration_hook(self.messages)

            # 1. Prepare schemas and messages
            tool_schemas = (
                []
                if no_tools
                else self.registry.get_schemas(tags=self.config.tool_tags)
            )

            # Use ContextManager to trim history based on token budget
            llm_messages = self.context_manager.prepare_messages(
                self.messages,
                max_history=self.config.max_history,
            )

            # Log history preview
            history_summary = []
            for m in llm_messages:
                role = m.get("role")
                content = m.get("content", "") or ""
                if isinstance(content, list):  # handle native tool results if any
                    content_str = str(content)
                else:
                    content_str = content
                history_summary.append(f"{role}({len(content_str)})")
            logger.debug(f"Calling LLM with history: {' -> '.join(history_summary)}")
            if self.config.verbose:
                for i, m in enumerate(llm_messages):
                    logger.debug(
                        f"  Message {i} [{m.get('role')}]: {repr(m.get('content'))[:200]}..."
                    )

            # 2. Call LLM (Streaming)
            self.cb.on_thinking_start()

            usage_obj = None
            final_content = ""
            final_reasoning = ""
            # We'll collect tool calls in both normalized and raw formats
            # (Raw is kept for appending to history exactly as it arrived)
            normalized_tool_calls = []
            raw_tool_calls_for_history: list[dict] = []
            thinking_stopped = False

            try:
                options: dict[str, Any] = {}
                if getattr(self.config, "num_ctx", None):
                    options["num_ctx"] = self.config.num_ctx
                if getattr(self.config, "max_output_tokens", None):
                    options["max_output_tokens"] = self.config.max_output_tokens
                if getattr(self.config, "stop_sequences", None):
                    options["stop_sequences"] = self.config.stop_sequences

                async_stream = self.llm.stream_with_tools(
                    llm_messages,
                    self.config.model,
                    tools=tool_schemas,
                    options=options,
                    verbose=self.config.verbose,
                )

                async for chunk in async_stream:
                    if chunk.usage:
                        usage_obj = chunk.usage

                    if chunk.reasoning:
                        final_reasoning += chunk.reasoning
                        self.cb.on_thinking_content(chunk.reasoning)

                    if chunk.content:
                        final_content += chunk.content
                        if not thinking_stopped:
                            thinking_stopped = True
                            self.cb.on_thinking_stop()
                        self.cb.on_assistant_content(chunk.content)

                    if chunk.tool_calls:
                        if not thinking_stopped:
                            thinking_stopped = True
                            self.cb.on_thinking_stop()
                        for tc in chunk.tool_calls:
                            # We use `_stream_index` if available, otherwise fallback to `len()` positioning
                            stream_idx = getattr(tc, "_stream_index", None)
                            
                            # Find if we are already building this tool call
                            existing_tc = None
                            
                            if stream_idx is not None:
                                # We have a strict index to match against (OpenAI/Deepseek/Ollama streams)
                                if stream_idx < len(raw_tool_calls_for_history):
                                    existing_tc = raw_tool_calls_for_history[stream_idx]
                            else:
                                # Fallback: try matching by ID
                                existing_tc = next(
                                    (x for x in raw_tool_calls_for_history if x["id"] == tc.id), 
                                    None
                                )
                            
                            if existing_tc is None:
                                # New tool call start
                                new_tc = {
                                    "id": tc.id,
                                    "type": "function",
                                    "function": {
                                        "name": tc.name, 
                                        "arguments": tc.arguments
                                    },
                                }
                                
                                # If we have a stream_index, ensure our array grows to that size
                                if stream_idx is not None:
                                    while len(raw_tool_calls_for_history) < stream_idx:
                                        raw_tool_calls_for_history.append({"id": f"dummy_{len(raw_tool_calls_for_history)}", "type": "function", "function": {"name": "", "arguments": ""}})
                                    raw_tool_calls_for_history.append(new_tc)
                                else:
                                    raw_tool_calls_for_history.append(new_tc)
                                    
                                # Only trigger UI start if we have a name
                                if tc.name:
                                    self.cb.on_tool_start(tc.id, tc.name, {})
                            else:
                                # Update ID if the existing one was a dummy or fallback ID, and the new one is real
                                if tc.id and not tc.id.startswith("idx_") and existing_tc["id"].startswith("idx_"):
                                    existing_tc["id"] = tc.id
                                    
                                # Append arguments to existing tool call
                                # Deepseek sends name ONLY on the first chunk, so we must catch it whenever it arrives
                                if tc.name and not existing_tc["function"]["name"]:
                                    existing_tc["function"]["name"] = tc.name
                                    self.cb.on_tool_start(existing_tc["id"], tc.name, {})
                                    
                                if tc.arguments:
                                    existing_tc["function"]["arguments"] += tc.arguments

                # Some models pack multiple parallel tool calls into one entry
                # with concatenated JSON args (e.g. '{...}{...}{...}'). Expand
                # these into individual tool calls before normalizing.
                raw_tool_calls_for_history = _expand_concatenated_tool_calls(
                    raw_tool_calls_for_history
                )

                # Now that streaming is done, build the normalized objects for execution
                for raw_tc in raw_tool_calls_for_history:
                    tool_call_obj = _ToolCall(
                        id=raw_tc["id"],
                        type="function",
                        function=_FunctionCall(
                            name=raw_tc["function"]["name"],
                            arguments=raw_tc["function"]["arguments"]
                        ),
                    )
                    normalized_tool_calls.append(tool_call_obj)

            except asyncio.CancelledError:
                logger.info("LLM stream cancelled")
                return
            except Exception as e:
                logger.exception("LLM stream failed")
                self.cb.on_system_message(f"Error: {e}")
                return
            finally:
                self.cb.on_thinking_stop()

            if self.cb.is_cancelled():
                return

            # Detect empty/dropped responses (server closed cleanly but sent nothing)
            if not final_content and not normalized_tool_calls and not final_reasoning:
                logger.warning(
                    "LLM returned empty response (possible connection drop). "
                    f"model={self.config.model}, provider={self.config.provider}"
                )
                self.cb.on_system_message(
                    "LLM returned an empty response. Check model compatibility "
                    "or try switching chat_protocol in config."
                )
                return

            # 3. Process final response metadata and token counting
            if usage_obj:
                # Use provider-reported token count if available
                tokens = usage_obj.get("total_tokens", 0)
                self._total_tokens += tokens
                self.context_manager.update_from_response(usage_obj)
            else:
                # No usage data from provider — estimate total tokens
                self._total_tokens += len(str(final_content)) // 4 + len(str(final_reasoning)) // 4
            self.cb.on_token_usage(self._total_tokens)

            logger.debug(f"LLM Response Content Length: {len(final_content)}")
            if final_reasoning:
                logger.debug(f"LLM Reasoning Length: {len(final_reasoning)}")

            if normalized_tool_calls:
                logger.debug(f"LLM Tool Calls: {len(normalized_tool_calls)}")

            # If model thought but forgot to output content/tools, prompt it
            if not final_content and not normalized_tool_calls and final_reasoning:
                logger.debug(
                    "Model thought but provided no content or tools. Prompting for final response."
                )
                self.messages.append(
                    {"role": "assistant", "content": f"<think>\n{final_reasoning}\n</think>"}
                )
                self.messages.append(
                    {
                        "role": "user",
                        "content": "Please provide your final response or tool call based on your reasoning above.",
                    }
                )
                continue

            # Build and append assistant message dict to conversation history.
            # Sanitize tool call arguments: some models emit malformed JSON which
            # gets stored in history. On the next API call, providers (e.g. Ollama)
            # validate the history and reject requests with invalid arguments.
            if raw_tool_calls_for_history:
                for tc_entry in raw_tool_calls_for_history:
                    raw_args = tc_entry["function"].get("arguments", "")
                    if isinstance(raw_args, str):
                        try:
                            json.loads(raw_args)
                        except (json.JSONDecodeError, ValueError):
                            logger.warning(
                                f"Malformed tool arguments for '{tc_entry['function'].get('name', '?')}': "
                                f"{raw_args!r:.200s} — repairing before storing in history"
                            )
                            parsed = _parse_arguments(raw_args)
                            tc_entry["function"]["arguments"] = json.dumps(parsed)

            msg_dict: dict = {"role": "assistant", "content": final_content}
            if raw_tool_calls_for_history:
                msg_dict["tool_calls"] = raw_tool_calls_for_history
            if final_reasoning:
                msg_dict["reasoning_content"] = final_reasoning

            self.messages.append(msg_dict)

            # 4. Handle tool execution
            if normalized_tool_calls:
                # We use the existing unified execution path
                escalated = await self._execute_tool_calls(normalized_tool_calls)
                if escalated:
                    self.cb.on_system_message(
                        "⚠ Escalation requested. Activity stopped; waiting for user prompt."
                    )
                    return
                no_tools = False
                continue

            # Text-only response — loop finished
            return

    # -- Tool execution ------------------------------------------------------

    async def _execute_tool_calls(self, tool_calls: List[_ToolCall]) -> bool:
        """Split auto-approved (parallel) vs needs-confirmation (sequential)."""
        tool_results_map = {}
        auto_approved = []
        needs_confirmation = []

        for tc in tool_calls:
            # Check for parsing errors injected by XML/JSON fallback protocols
            if getattr(tc, "error", None):
                rd = {
                    "tool_call_id": tc.id,
                    "name": "parse_error",
                    "result": f"Error: {tc.error}",  # type: ignore[attr-defined]
                }
                tool_results_map[tc.id] = rd
                self.cb.on_tool_start(tc.id, "parse_error", {})
                self.cb.on_tool_complete(tc.id, rd["result"])
                continue

            if not tc.function.name or tc.function.name == "unknown":
                rd = {
                    "tool_call_id": tc.id,
                    "name": "unknown",
                    "result": "Error: tool name is empty or unknown. You must specify a valid function name.",
                }
                tool_results_map[tc.id] = rd
                self.cb.on_tool_start(tc.id, "unknown", {})
                self.cb.on_tool_complete(tc.id, rd["result"])
                continue

            # Validate that arguments parsed correctly — some providers
            # (e.g. DeepSeek) send empty/malformed arguments in the native
            # tool call while putting the real content in reasoning.
            args = _parse_arguments(tc.function.arguments)
            missing = _check_required_args(tc.function.name, args)
            if missing:
                err_msg = (
                    f"Error: tool call '{tc.function.name}' has missing required "
                    f"arguments: {', '.join(missing)}. "
                    f"Raw arguments received: {tc.function.arguments!r}. "
                    f"You must provide all required arguments in the function call."
                )
                rd = {
                    "tool_call_id": tc.id,
                    "name": tc.function.name,
                    "result": err_msg,
                }
                tool_results_map[tc.id] = rd
                self.cb.on_tool_start(tc.id, tc.function.name, args)
                self.cb.on_tool_complete(tc.id, err_msg)
                logger.warning(
                    f"Tool '{tc.function.name}' called with missing args {missing}. "
                    f"Raw: {tc.function.arguments!r}"
                )
                continue

            if self._tool_needs_confirmation(tc.function.name):
                needs_confirmation.append(tc)
            else:
                auto_approved.append(tc)

        # Show non-empty tools as running
        for tc in tool_calls:
            if tc.id in tool_results_map:
                continue
            args = _parse_arguments(tc.function.arguments)
            self.cb.on_tool_start(tc.id, tc.function.name, args)

        escalated = False

        # Auto-approved in parallel via asyncio.as_completed for speculative background execution
        if auto_approved:

            async def _safe_exec(tc_obj):
                try:
                    return tc_obj, await self._exec_tool_async(tc_obj)
                except asyncio.CancelledError:
                    logger.warning(f"Tool execution cancelled: {tc_obj.function.name}")
                    return tc_obj, RuntimeError("Tool execution cancelled")
                except Exception as e:
                    logger.warning(f"Tool execution failed for '{tc_obj.function.name}': {e}")
                    return tc_obj, e

            tasks = [asyncio.create_task(_safe_exec(tc)) for tc in auto_approved]

            for completed_task in asyncio.as_completed(tasks):
                tc, rd = await completed_task
                tool_results_map[tc.id] = rd

                # Notify UI immediately
                if isinstance(rd, dict):
                    tid = rd["tool_call_id"]
                    name = rd["name"]
                    result = str(rd["result"])
                    result = truncate_tool_result(result)
                    self.cb.on_tool_complete(tid, result)
                else:
                    self.cb.on_tool_complete(tc.id, f"Error: {rd}")

        # Needs-confirmation sequentially
        custom_instructions = None
        for tc in needs_confirmation:
            name = tc.function.name
            args = _parse_arguments(tc.function.arguments)

            confirm = await self.cb.request_confirmation(name, args)

            if confirm is not None and getattr(confirm, "action", None) == "approve":
                policy = ExecutionPolicy(self.config.permissions)
                exec_result = await asyncio.to_thread(
                    policy.execute_with_registry,
                    ToolRequest(name, args),
                    self.registry,
                    pre_approved=True,
                )
                result = _unwrap_exec_result(exec_result)
                rd = {"tool_call_id": tc.id, "name": name, "result": result}
                tool_results_map[tc.id] = rd

                # Notify UI
                self.cb.on_tool_complete(tc.id, result)

            elif confirm is not None and getattr(confirm, "action", None) == "instruct":
                # User provided instructions instead of approval
                custom_instructions = getattr(confirm, "instructions", None)
                denied_msg = "Tool call skipped by user instruction."
                rd = {"tool_call_id": tc.id, "name": name, "result": denied_msg}
                tool_results_map[tc.id] = rd
                self.cb.on_tool_complete(tc.id, denied_msg)
                break  # Stop processing further tools if we got an instruction
            else:
                # User denied tool — still must add a result so the LLM sees
                # a valid tool_call → tool_result sequence (required by API)
                denied_msg = "Tool call denied by user."
                rd = {"tool_call_id": tc.id, "name": name, "result": denied_msg}
                tool_results_map[tc.id] = rd
                self.cb.on_tool_complete(tc.id, denied_msg)

        # Ensure every tool_call has a result (API requires it)
        for tc in tool_calls:
            if tc.id not in tool_results_map:
                skipped_msg = "Tool call skipped."
                tool_results_map[tc.id] = {
                    "tool_call_id": tc.id,
                    "name": tc.function.name,
                    "result": skipped_msg,
                }
                self.cb.on_tool_complete(tc.id, skipped_msg)

        # Process results in correct order -> append tool messages
        for tc in tool_calls:
            rd_result: dict[str, Any] | None = tool_results_map.get(tc.id)
            if rd_result is None:
                continue

            if isinstance(rd_result, dict):
                tid = rd_result["tool_call_id"]
                name = rd_result["name"]
                result = str(rd_result["result"])

                logger.debug(f"Appending Tool Result [{name}] to history:\n{result[:500]}")

                escalated = escalated or _is_escalation_result(result)
                self.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tid,
                        "name": name,
                        "content": result,
                    }
                )
            else:
                # rd_result is BaseException (includes Exception)
                err_id, err_name = tc.id, tc.function.name
                error_msg = f"Error: {rd_result}"
                logger.debug(f"Appending Tool Error [{err_name}] to history:\n{error_msg}")
                self.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": err_id,
                        "name": err_name,
                        "content": error_msg,
                    }
                )

        if custom_instructions:
            self.messages.append({"role": "user", "content": custom_instructions})

        self.cb.on_tools_cleanup()
        return escalated

    async def _exec_tool_async(self, tc) -> dict:
        """Execute a single tool call through the shared execution policy path."""
        name = tc.function.name
        args = _parse_arguments(tc.function.arguments)
        policy = ExecutionPolicy(self.config.permissions)
        exec_result = await asyncio.to_thread(
            policy.execute_with_registry,
            ToolRequest(name, args),
            self.registry,
            pre_approved=True,
        )
        result = _unwrap_exec_result(exec_result)
        return {"tool_call_id": tc.id, "name": name, "result": result}

    # -- Helpers -------------------------------------------------------------

    def _tool_needs_confirmation(self, tool_name: str) -> bool:
        """Delegate to shared ExecutionPolicy — same check for CLI and TUI."""
        policy = ExecutionPolicy(self.config.permissions)
        return policy.get_confirmation_requirement(tool_name).requires_confirmation


def _parse_arguments(arguments) -> dict:
    """Safely parse tool call arguments (str or dict).

    When the LLM hits its output token limit, the streamed JSON may be
    truncated (e.g. ``{"file_path": "foo", "content": "abc...``).
    We attempt ``json.loads`` first; on failure we try to repair the
    truncated JSON by closing open strings/braces before giving up.
    """
    if isinstance(arguments, dict):
        return arguments
    if isinstance(arguments, str):
        try:
            return json.loads(arguments)
        except (json.JSONDecodeError, ValueError):
            logger.warning(f"Tool arguments JSON parse failed: {arguments!r:.200s}")
            # Try extracting just the first JSON object (handles concatenated
            # JSON like '{...}{...}' that slipped past expansion).
            try:
                obj, _ = json.JSONDecoder().raw_decode(arguments.strip())
                if isinstance(obj, dict):
                    logger.warning("Recovered tool arguments via raw_decode")
                    return obj
            except (json.JSONDecodeError, ValueError):
                pass
            repaired = _repair_truncated_json(arguments)
            if repaired is not None:
                logger.warning("Recovered tool arguments via truncated JSON repair")
                return repaired
            logger.warning("Could not recover tool arguments — using empty dict")
            return {}
    return {}


def _repair_truncated_json(raw: str) -> dict | None:
    """Best-effort repair of a truncated JSON object.

    Handles the common case where the model's output was cut off mid-value,
    e.g. ``{"file_path": "x.py", "operation": "write", "content": "hel``
    We try progressively trimming from the end and closing brackets.
    """
    if not raw or not raw.lstrip().startswith("{"):
        return None

    # Try closing increasingly shorter prefixes
    for trim in range(0, min(len(raw), 200), 1):
        candidate = raw if trim == 0 else raw[:-trim]
        # Try closing with various suffixes
        for suffix in ['"}', '"}]}', '"}}', '}', ']}', '"]:}', '"}']:
            try:
                result = json.loads(candidate + suffix)
                if isinstance(result, dict):
                    return result
            except (json.JSONDecodeError, ValueError):
                continue  # Expected: trying multiple repair suffixes
    return None


def _check_required_args(tool_name: str, parsed_args: dict) -> list[str]:
    """Return list of missing or empty required arguments for a tool."""
    from ayder_cli.tools.definition import TOOL_DEFINITIONS_BY_NAME

    tool_def = TOOL_DEFINITIONS_BY_NAME.get(tool_name)
    if not tool_def or not tool_def.parameters:
        return []
    required = tool_def.parameters.get("required", [])
    # Check both missing keys and empty-string values
    missing = []
    for r in required:
        val = parsed_args.get(r)
        if val is None or (isinstance(val, str) and not val.strip()):
            missing.append(r)
    return missing


def _unwrap_exec_result(exec_result) -> str:
    """Unwrap ExecutionResult or raw string (test mocks may return str)."""
    if hasattr(exec_result, "success"):
        return exec_result.result if exec_result.success else str(exec_result.error)
    return str(exec_result)


def _expand_concatenated_tool_calls(raw_tool_calls: list[dict]) -> list[dict]:
    """Split tool calls whose arguments contain multiple concatenated JSON objects.

    Some models emit all parallel tool calls as a single native tool call with
    arguments like '{...}{...}{...}' instead of separate tool call entries.
    Uses json.JSONDecoder.raw_decode to extract each object without loading the
    whole string at once.
    """
    result = []
    decoder = json.JSONDecoder()
    for raw_tc in raw_tool_calls:
        args_str = raw_tc["function"].get("arguments", "")
        if not isinstance(args_str, str):
            result.append(raw_tc)
            continue
        objects: list[str] = []
        pos = 0
        stripped = args_str.strip()
        while pos < len(stripped):
            try:
                obj, end_pos = decoder.raw_decode(stripped, pos)
                objects.append(json.dumps(obj))
                pos = end_pos
                while pos < len(stripped) and stripped[pos] in " \t\n\r":
                    pos += 1
            except json.JSONDecodeError:
                if pos > 0:
                    logger.warning(
                        f"Concatenated tool call JSON parse stopped at pos {pos}/{len(stripped)}"
                    )
                break
        if len(objects) > 1:
            logger.debug(
                f"Expanding concatenated tool call '{raw_tc['function']['name']}' "
                f"into {len(objects)} separate calls"
            )
            for i, args in enumerate(objects):
                result.append({
                    "id": f"{raw_tc['id']}_split_{i}",
                    "type": "function",
                    "function": {"name": raw_tc["function"]["name"], "arguments": args},
                })
        else:
            result.append(raw_tc)
    return result


def _is_escalation_result(result_text: str) -> bool:
    """Detect escalation directive in tool result payload."""
    try:
        payload = json.loads(result_text)
    except (json.JSONDecodeError, TypeError, ValueError):
        return False  # Not JSON — normal for most tool results, not an error
    if not isinstance(payload, dict):
        return False

    action = payload.get("action")
    action_control = payload.get("action_control")
    return action == "escalate" or action_control == "escalate"
