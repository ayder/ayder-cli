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

from ayder_cli.client import call_llm_async
from ayder_cli.parser import parse_custom_tool_calls
from ayder_cli.tools.schemas import TOOL_PERMISSIONS

# Import TUI parser components
from ayder_cli.tui.parser import (
    content_processor,
    has_custom_tool_calls,
)

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
    max_iterations: int = 50
    permissions: set = field(default_factory=lambda: {"r"})


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


class TuiChatLoop:
    """Async chat loop that drives the TUI's LLM pipeline.

    Owns: iteration counting, LLM calls, tool parsing/execution,
    checkpoint triggering. Does NOT own any Textual widgets.
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
        self.llm = llm
        self.registry = registry
        self.messages = messages
        self.config = config
        self.cb = callbacks
        self.cm = checkpoint_manager
        self.mm = memory_manager
        self._iteration = 0
        self._total_tokens = 0

    # -- public API ----------------------------------------------------------

    @property
    def iteration(self) -> int:
        return self._iteration

    @property
    def total_tokens(self) -> int:
        return self._total_tokens

    def reset_iterations(self) -> None:
        self._iteration = 0

    async def run(self, *, no_tools: bool = False) -> None:
        """Main loop: call LLM, handle tools, repeat until text-only or cancel."""
        while True:
            if self.cb.is_cancelled():
                return

            self._iteration += 1
            self.cb.on_iteration_update(self._iteration, self.config.max_iterations)
            if self._iteration > self.config.max_iterations:
                if not await self._handle_checkpoint():
                    self.cb.on_system_message(
                        f"Reached max iterations ({self.config.max_iterations})."
                    )
                    return

            # 1. Call LLM
            self.cb.on_thinking_start()
            try:
                tool_schemas = [] if no_tools else self.registry.get_schemas()
                response = await call_llm_async(
                    self.llm,
                    self.messages,
                    self.config.model,
                    tools=tool_schemas,
                    num_ctx=self.config.num_ctx,
                )
            except Exception as e:
                self.cb.on_thinking_stop()
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
                await self._execute_openai_tool_calls(tool_calls)
                no_tools = False
                continue

            # Check for custom tool calls (including namespaced variants like <minimax:tool_call>
            # and DeepSeek format like <function_calls>)
            if content and has_custom_tool_calls(content):
                custom_calls = parse_custom_tool_calls(content)
                valid = [c for c in custom_calls if "error" not in c]
                if valid:
                    await self._execute_custom_tool_calls(valid)
                    no_tools = False
                    continue

            # JSON fallback: model outputs tool calls as a JSON array in content
            json_calls = content_processor.parse_json_tool_calls(content)
            if json_calls:
                await self._execute_custom_tool_calls(json_calls)
                no_tools = False
                continue

            # Text-only response — done
            return

    # -- OpenAI tool calls ---------------------------------------------------

    async def _execute_openai_tool_calls(self, tool_calls) -> None:
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
                result = await asyncio.to_thread(self.registry.execute, name, args)
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

    async def _exec_tool_async(self, tc) -> dict:
        """Execute a single tool call asynchronously."""
        name = tc.function.name
        args = _parse_arguments(tc.function.arguments)
        result = await asyncio.to_thread(self.registry.execute, name, args)
        return {"tool_call_id": tc.id, "name": name, "result": result}

    # -- Custom XML tool calls -----------------------------------------------

    async def _execute_custom_tool_calls(self, calls: list[dict]) -> None:
        """Execute XML-parsed tool calls and append user-role results."""
        results_text = []
        for call in calls:
            name = call.get("name", "unknown")
            args = call.get("arguments", {})
            call_id = f"xml-{name}-{id(call)}"
            self.cb.on_tool_start(call_id, name, args)
            try:
                result = await asyncio.to_thread(self.registry.execute, name, args)
                results_text.append(f"[{name}] {result}")
                self.cb.on_tool_complete(call_id, str(result))
            except Exception as e:
                results_text.append(f"[{name}] Error: {e}")
                self.cb.on_tool_complete(call_id, f"Error: {e}")

        self.messages.append({"role": "user", "content": "\n".join(results_text)})
        self.cb.on_tools_cleanup()

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
            )
        except Exception:
            self.cb.on_thinking_stop()
            return False
        finally:
            self.cb.on_thinking_stop()

        summary_content = response.choices[0].message.content or conversation_summary
        self.cm.save_checkpoint(summary_content)

        # 3. Reset messages (keep system prompt) and restore context
        system_msg = (
            self.messages[0]
            if self.messages and self.messages[0].get("role") == "system"
            else None
        )
        self.messages.clear()
        if system_msg:
            self.messages.append(system_msg)

        restore_msg = (
            self.mm.build_quick_restore_message()
            if self.mm
            else f"[SYSTEM: Context reset. Previous summary saved.]\n\n{summary_content}\n\nPlease continue."
        )
        self.messages.append({"role": "user", "content": restore_msg})

        self._iteration = 0
        self.cb.on_system_message("Checkpoint saved — context compacted. Continuing...")
        return True

    # -- Helpers -------------------------------------------------------------

    def _tool_needs_confirmation(self, tool_name: str) -> bool:
        perm = TOOL_PERMISSIONS.get(tool_name, "r")
        return perm not in self.config.permissions


# -- Backward-compat wrappers (keep test imports working) -------------------


def _extract_think_blocks(content: str) -> list[str]:
    return content_processor.extract_think_blocks(content)


def _strip_tool_markup(content: str) -> str:
    return content_processor.strip_for_display(content)


def _parse_json_tool_calls(content: str) -> list[dict]:
    return content_processor.parse_json_tool_calls(content)


def _regex_extract_json_tool_calls(content: str) -> list[dict]:
    return content_processor._regex_extract_json_tool_calls(content)


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
