"""
TuiChatLoop — async chat loop for the Textual TUI.

Extracts all LLM call + tool execution logic from app.py into a testable,
widget-free class. Communication with Textual widgets happens exclusively
through the TuiCallbacks protocol.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from ayder_cli.application.checkpoint_orchestrator import (
    CheckpointOrchestrator,
    EngineState,
)
from ayder_cli.application.execution_policy import ExecutionPolicy, ToolRequest
from ayder_cli.client import call_llm_async
from ayder_cli.loops.base import AgentLoopBase
from ayder_cli.parser import content_processor

if TYPE_CHECKING:
    from ayder_cli.checkpoint_manager import CheckpointManager
    from ayder_cli.memory import MemoryManager
    from ayder_cli.services.llm import LLMProvider
    from ayder_cli.tools.registry import ToolRegistry


@dataclass
class TuiLoopConfig:
    """Configuration for the TUI chat loop."""

    model: str = "qwen3-coder:latest"
    num_ctx: int = 65536
    max_output_tokens: int = 4096
    stop_sequences: list = field(default_factory=list)
    max_iterations: int = 50
    permissions: set = field(default_factory=lambda: {"r"})
    tool_tags: frozenset | None = None
    max_history: int = 0


@runtime_checkable
class TuiCallbacks(Protocol):
    """Protocol so TuiChatLoop never touches Textual widgets directly."""

    def on_thinking_start(self) -> None: ...
    def on_thinking_stop(self) -> None: ...
    def on_assistant_content(self, text: str) -> None: ...
    def on_thinking_content(self, text: str) -> None: ...
    def on_token_usage(self, total_tokens: int) -> None: ...
    def on_iteration_update(self, current: int, maximum: int) -> None: ...
    def on_tool_start(self, call_id: str, name: str, arguments: dict) -> None: ...
    def on_tool_complete(self, call_id: str, result: str) -> None: ...
    def on_tools_cleanup(self) -> None: ...
    def on_system_message(self, text: str) -> None: ...
    async def request_confirmation(
        self, name: str, arguments: dict
    ) -> object | None: ...
    def is_cancelled(self) -> bool: ...


class TuiChatLoop(AgentLoopBase):
    """Async chat loop that drives the TUI's LLM pipeline.

    Extends AgentLoopBase for shared iteration counting, checkpoint trigger
    detection, tool call routing, and escalation detection.
    Does NOT own any Textual widgets.
    """

    def __init__(
        self,
        llm: LLMProvider,
        registry: ToolRegistry,
        messages: list[dict],
        config: TuiLoopConfig,
        callbacks: TuiCallbacks,
        checkpoint_manager: CheckpointManager | None = None,
        memory_manager: MemoryManager | None = None,
    ) -> None:
        super().__init__(config)
        self.llm = llm
        self.registry = registry
        self.messages = messages
        self.config = config
        self.cb = callbacks
        self.cm = checkpoint_manager
        self.mm = memory_manager
        self._total_tokens = 0

    # -- public API ----------------------------------------------------------

    @property
    def total_tokens(self) -> int:
        return self._total_tokens

    async def run(self, *, no_tools: bool = False) -> None:
        """Main loop: call LLM, handle tools, repeat until text-only or cancel."""
        while True:
            if self.cb.is_cancelled():
                return

            self._increment_iteration()
            self.cb.on_iteration_update(self._iteration, self.config.max_iterations)
            if self._should_trigger_checkpoint():
                if not await self._handle_checkpoint():
                    self.cb.on_system_message(
                        f"Reached max iterations ({self.config.max_iterations})."
                    )
                    return

            # 1. Call LLM
            # Apply sliding-window truncation when max_history is set
            if self.config.max_history > 0 and len(self.messages) > self.config.max_history + 1:
                llm_messages = [self.messages[0]] + self.messages[-(self.config.max_history):]
            else:
                llm_messages = self.messages

            self.cb.on_thinking_start()
            try:
                tool_schemas = (
                    [] if no_tools
                    else self.registry.get_schemas(tags=self.config.tool_tags)
                )
                response = await call_llm_async(
                    self.llm,
                    llm_messages,
                    self.config.model,
                    tools=tool_schemas,
                    num_ctx=self.config.num_ctx,
                    max_output_tokens=self.config.max_output_tokens,
                    stop_sequences=self.config.stop_sequences or None,
                )
            except Exception as e:
                self.cb.on_system_message(f"Error: {e}")
                return
            finally:
                self.cb.on_thinking_stop()

            if self.cb.is_cancelled():
                return

            # 2. Process response metadata
            usage = getattr(response, "usage", None)
            if usage:
                tokens = getattr(usage, "total_tokens", 0) or 0
                self._total_tokens += tokens
                self.cb.on_token_usage(self._total_tokens)

            message = response.choices[0].message
            content = message.content or ""
            tool_calls = message.tool_calls

            # 3. Build and append assistant message dict
            msg_dict: dict = {"role": "assistant", "content": content}
            if tool_calls:
                msg_dict["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": tc.type,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in tool_calls
                ]
            self.messages.append(msg_dict)

            # 4. Extract <think> blocks
            think_blocks = content_processor.extract_think_blocks(content)
            for text in think_blocks:
                self.cb.on_thinking_content(text)

            # 5. Strip tool markup and display content
            display = content_processor.strip_for_display(content)
            if display:
                self.cb.on_assistant_content(display)

            # 6. Route: OpenAI tool_calls → XML fallback → JSON fallback → done
            if tool_calls:
                escalated = await self._execute_openai_tool_calls(tool_calls)
                if escalated:
                    self.cb.on_system_message(
                        "⚠ Escalation requested. Activity stopped; waiting for user prompt."
                    )
                    return
                no_tools = False
                continue

            # Check for custom tool calls (including namespaced variants like <minimax:tool_call>
            # and DeepSeek format like <function_calls>)
            if content and content_processor.has_tool_calls(content):
                custom_calls = content_processor.parse_tool_calls(content)
                valid = [c for c in custom_calls if "error" not in c]
                if valid:
                    escalated = await self._execute_custom_tool_calls(valid)
                    if escalated:
                        self.cb.on_system_message(
                            "⚠ Escalation requested. Activity stopped; waiting for user prompt."
                        )
                        return
                    no_tools = False
                    continue

            # JSON fallback: model outputs tool calls as a JSON array in content
            json_calls = content_processor.parse_json_tool_calls(content)
            if json_calls:
                escalated = await self._execute_custom_tool_calls(json_calls)
                if escalated:
                    self.cb.on_system_message(
                        "⚠ Escalation requested. Activity stopped; waiting for user prompt."
                    )
                    return
                no_tools = False
                continue

            # Text-only response — done
            return

    # -- OpenAI tool calls ---------------------------------------------------

    async def _execute_openai_tool_calls(self, tool_calls) -> bool:
        """Split auto-approved (parallel) vs needs-confirmation (sequential)."""
        auto_approved = []
        needs_confirmation = []
        for tc in tool_calls:
            if self._tool_needs_confirmation(tc.function.name):
                needs_confirmation.append(tc)
            else:
                auto_approved.append(tc)

        # Show all tools as running
        for tc in tool_calls:
            args = _parse_arguments(tc.function.arguments)
            self.cb.on_tool_start(tc.id, tc.function.name, args)

        tool_results: list[dict | BaseException] = []
        escalated = False

        # Auto-approved in parallel
        if auto_approved:
            tasks = [self._exec_tool_async(tc) for tc in auto_approved]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            tool_results.extend(results)

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
                tool_results.append(
                    {"tool_call_id": tc.id, "name": name, "result": result}
                )
            elif confirm is not None and getattr(confirm, "action", None) == "instruct":
                tool_results.append(
                    {
                        "tool_call_id": tc.id,
                        "name": name,
                        "result": "Tool call denied by user.",
                    }
                )
                custom_instructions = getattr(confirm, "instructions", None)
                # Skip remaining
                idx = needs_confirmation.index(tc)
                for remaining in needs_confirmation[idx + 1 :]:
                    tool_results.append(
                        {
                            "tool_call_id": remaining.id,
                            "name": remaining.function.name,
                            "result": "Tool call skipped (user provided instructions).",
                        }
                    )
                break
            else:
                tool_results.append(
                    {
                        "tool_call_id": tc.id,
                        "name": name,
                        "result": "Tool call denied by user.",
                    }
                )

        # Process results → append tool messages
        for i, rd in enumerate(tool_results):
            if isinstance(rd, dict):
                tid = rd["tool_call_id"]
                name = rd["name"]
                result = rd["result"]
                escalated = escalated or _is_escalation_result(str(result))
                self.cb.on_tool_complete(tid, str(result))
                self.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tid,
                        "name": name,
                        "content": str(result),
                    }
                )
            else:
                # rd is BaseException (includes Exception)
                if i < len(auto_approved):
                    err_tc = auto_approved[i]
                    err_id, err_name = err_tc.id, err_tc.function.name
                else:
                    err_id, err_name = "error", "unknown"
                error_msg = f"Error: {rd}"
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
            policy.execute_with_registry, ToolRequest(name, args), self.registry
        )
        result = _unwrap_exec_result(exec_result)
        return {"tool_call_id": tc.id, "name": name, "result": result}

    # -- Custom XML tool calls -----------------------------------------------

    async def _execute_custom_tool_calls(self, calls: list[dict]) -> bool:
        """Execute XML-parsed tool calls through the shared execution policy path."""
        policy = ExecutionPolicy(self.config.permissions)
        results_text = []
        escalated = False
        custom_instructions = None

        for call in calls:
            name = call.get("name", "unknown")
            args = call.get("arguments", {})
            call_id = f"xml-{name}-{id(call)}"
            self.cb.on_tool_start(call_id, name, args)

            # Confirmation gate — mirrors _execute_openai_tool_calls behavior
            pre_approved = False
            if self._tool_needs_confirmation(name):
                confirm = await self.cb.request_confirmation(name, args)
                action = getattr(confirm, "action", None) if confirm is not None else None
                if action == "approve":
                    pre_approved = True
                elif action == "instruct":
                    custom_instructions = getattr(confirm, "instructions", None)
                    results_text.append(f"[{name}] Tool call denied by user.")
                    self.cb.on_tool_complete(call_id, "Tool call denied by user.")
                    break
                else:
                    results_text.append(f"[{name}] Tool call denied by user.")
                    self.cb.on_tool_complete(call_id, "Tool call denied by user.")
                    continue

            try:
                exec_result = await asyncio.to_thread(
                    policy.execute_with_registry,
                    ToolRequest(name, args),
                    self.registry,
                    pre_approved=pre_approved,
                )
                result = exec_result.result if exec_result.success else str(exec_result.error)
                result = result or ""
                escalated = escalated or _is_escalation_result(str(result))
                results_text.append(f"[{name}] {result}")
                self.cb.on_tool_complete(call_id, result)
            except Exception as e:
                results_text.append(f"[{name}] Error: {e}")
                self.cb.on_tool_complete(call_id, f"Error: {e}")

        self.messages.append({"role": "user", "content": "\n".join(results_text)})
        if custom_instructions:
            self.messages.append({"role": "user", "content": custom_instructions})
        self.cb.on_tools_cleanup()
        return escalated

    # -- Checkpoint ----------------------------------------------------------

    async def _handle_checkpoint(self) -> bool:
        """Create a memory checkpoint, reset messages, restore context.

        Returns True if the loop should continue with a fresh context.
        """
        if not self.cm:
            return False

        # 1. Build a conversation summary from recent messages
        from ayder_cli.application.message_contract import (
            get_message_role,
            get_message_content,
        )

        summary_parts = []
        for msg in self.messages[-10:]:
            role = get_message_role(msg)
            content = get_message_content(msg)
            if content:
                summary_parts.append(f"[{role}] {content[:200]}")
        conversation_summary = "\n".join(summary_parts)

        # 2. Ask LLM to produce a checkpoint summary (no tools)
        from ayder_cli.prompts import MEMORY_CHECKPOINT_PROMPT_TEMPLATE
        from ayder_cli.checkpoint_manager import CHECKPOINT_FILE_NAME

        checkpoint_prompt = MEMORY_CHECKPOINT_PROMPT_TEMPLATE.format(
            conversation_summary=conversation_summary,
            memory_file_name=CHECKPOINT_FILE_NAME,
        )
        checkpoint_messages = list(self.messages) + [
            {"role": "user", "content": checkpoint_prompt}
        ]

        self.cb.on_system_message(
            "Approaching iteration limit — creating memory checkpoint..."
        )
        self.cb.on_thinking_start()
        try:
            response = await call_llm_async(
                self.llm,
                checkpoint_messages,
                self.config.model,
                tools=[],
                num_ctx=self.config.num_ctx,
                max_output_tokens=self.config.max_output_tokens,
            )
        except Exception:
            return False
        finally:
            self.cb.on_thinking_stop()

        summary_content = response.choices[0].message.content or conversation_summary

        # 3. Delegate reset/restore to shared orchestrator — no per-loop transition logic
        orchestrator = CheckpointOrchestrator()
        state = EngineState(iteration=self._iteration, messages=list(self.messages))
        restore_msg = orchestrator.orchestrate_checkpoint(
            state, summary_content, self.cm, self.mm
        )

        # Apply state back to live message list
        self.messages.clear()
        self.messages.extend(m for m in state.messages if m.get("role") == "system")
        self.messages.append({"role": "user", "content": restore_msg})

        self._reset_iterations()
        self.cb.on_system_message("Checkpoint saved — context compacted. Continuing...")
        return True

    # -- Helpers -------------------------------------------------------------

    def _tool_needs_confirmation(self, tool_name: str) -> bool:
        """Delegate to shared ExecutionPolicy — same check for CLI and TUI."""
        policy = ExecutionPolicy(self.config.permissions)
        return policy.get_confirmation_requirement(tool_name).requires_confirmation


def _parse_arguments(arguments) -> dict:
    """Safely parse tool call arguments (str or dict)."""
    if isinstance(arguments, dict):
        return arguments
    if isinstance(arguments, str):
        try:
            return json.loads(arguments)
        except (json.JSONDecodeError, ValueError):
            return {}
    return {}


def _unwrap_exec_result(exec_result) -> str:
    """Unwrap ExecutionResult or raw string (test mocks may return str)."""
    if hasattr(exec_result, "success"):
        return exec_result.result if exec_result.success else str(exec_result.error)
    return str(exec_result)


def _is_escalation_result(result_text: str) -> bool:
    """Detect escalation directive in tool result payload."""
    try:
        payload = json.loads(result_text)
    except (json.JSONDecodeError, TypeError, ValueError):
        return False
    if not isinstance(payload, dict):
        return False

    action = payload.get("action")
    action_control = payload.get("action_control")
    return action == "escalate" or action_control == "escalate"
