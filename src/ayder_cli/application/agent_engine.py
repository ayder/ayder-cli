"""Shared Async Agent Engine — single source of orchestration truth.

Used by both CLI (via asyncio.run) and TUI (awaited in worker lifecycle).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional

from ayder_cli.tools.schemas import TOOL_PERMISSIONS


@dataclass
class EngineConfig:
    """Configuration for AgentEngine."""

    model: str = "qwen3-coder:latest"
    num_ctx: int = 65536
    max_iterations: int = 50
    permissions: set = field(default_factory=lambda: {"r"})
    initial_iteration: int = 0


class AgentEngine:
    """Shared async orchestration engine for CLI and TUI.

    Handles: iteration control, LLM call loop, tool call routing,
    checkpoint trigger integration, cancellation, callback notifications.
    """

    def __init__(
        self,
        llm_provider: Any,
        tool_registry: Any,
        config: EngineConfig,
        callbacks: Any = None,
        checkpoint_manager: Any = None,
        memory_manager: Any = None,
    ) -> None:
        self.llm = llm_provider
        self.registry = tool_registry
        self.config = config
        self.cb = callbacks
        self.cm = checkpoint_manager
        self.mm = memory_manager

    async def run(
        self, messages: list, user_input: str | None = None
    ) -> Optional[str]:
        """Main async agent loop.

        Args:
            messages: Conversation history (mutated in-place with assistant/tool msgs).
            user_input: Optional user message to prepend before looping.

        Returns:
            Final assistant text response, or None if cancelled.
        """
        if user_input is not None:
            messages.append({"role": "user", "content": user_input})

        # Restore from checkpoint if available at startup
        if self.cm is not None and self.mm is not None:
            try:
                if self.cm.has_saved_checkpoint():
                    self.mm.restore_from_checkpoint()
            except Exception:
                pass

        iteration = self.config.initial_iteration
        # Track processed tool_call_ids to avoid re-executing in stuck loops
        _processed_tool_ids: set[str] = set()

        while True:
            # Check cancellation before each iteration
            if self.cb is not None and self.cb.is_cancelled():
                return None

            iteration += 1
            if self.cb is not None:
                self.cb.on_iteration_update(iteration, self.config.max_iterations)

            # Max iterations: try checkpoint, otherwise terminate
            if iteration > self.config.max_iterations:
                checkpoint_continued = await self._handle_checkpoint(messages)
                if not checkpoint_continued:
                    if self.cb is not None:
                        self.cb.on_system_message(
                            f"Reached max iterations ({self.config.max_iterations})."
                        )
                    return None
                # Checkpoint succeeded: reset iteration and fall through to LLM call
                iteration = 0

            # Call LLM
            if self.cb is not None:
                self.cb.on_thinking_start()
            try:
                tool_schemas = self.registry.get_schemas() if hasattr(self.registry, "get_schemas") else []
                response = await self._call_llm(
                    messages, self.config.model, tool_schemas, self.config.num_ctx
                )
            except Exception as e:
                if self.cb is not None:
                    self.cb.on_thinking_stop()
                    self.cb.on_system_message(f"Error: {e}")
                return None
            finally:
                if self.cb is not None:
                    self.cb.on_thinking_stop()

            if self.cb is not None and self.cb.is_cancelled():
                return None

            # Extract content/tool_calls/tokens from response
            content, tool_calls, total_tokens = _parse_response(response)

            # Token usage callback
            if self.cb is not None and total_tokens:
                self.cb.on_token_usage(total_tokens)

            # Append assistant message
            msg_dict: dict = {"role": "assistant", "content": content}
            if tool_calls:
                msg_dict["tool_calls"] = _serialize_tool_calls(tool_calls)
            messages.append(msg_dict)

            # Notify content (think blocks, display text)
            await self._on_response_content(content, tool_calls)

            # Text-only → check XML/JSON custom tool call fallback, then done
            if not tool_calls:
                custom_calls = await self._parse_custom_tool_calls(content)
                if custom_calls:
                    await self._execute_custom_tool_calls(custom_calls, messages)
                    await self._after_tool_batch()
                    continue
                return content or None

            # Route tool calls
            await self._execute_tool_calls(tool_calls, messages, _processed_tool_ids)
            await self._after_tool_batch()

    # -- Tool execution -------------------------------------------------------

    async def _execute_tool_calls(
        self, tool_calls: list, messages: list, processed_ids: set
    ) -> None:
        """Execute tool calls and append results to messages.

        Skips tool calls whose IDs have already been processed in this run,
        preventing infinite loops when the LLM returns the same tool call
        repeatedly (e.g., in mocked/test environments).
        """
        for tc in tool_calls:
            name = _tc_name(tc)
            args = _tc_arguments(tc)
            call_id = _tc_id(tc)

            # Skip already-processed tool calls to avoid re-execution loops
            if call_id in processed_ids:
                continue

            if self.cb is not None:
                self.cb.on_tool_start(call_id, name, args)

            # Confirm if tool needs confirmation
            if self._needs_confirmation(name):
                confirm = await self.cb.request_confirmation(name, args)
                action = confirm.get("action") if isinstance(confirm, dict) else getattr(confirm, "action", None)
                if action != "approve":
                    result = "Tool call denied by user."
                    if self.cb is not None:
                        self.cb.on_tool_complete(call_id, result)
                    processed_ids.add(call_id)
                    messages.append({"role": "tool", "tool_call_id": call_id, "name": name, "content": result})
                    stop, inject = await self._on_deny(confirm, tool_calls, tc, processed_ids, messages)
                    if inject is not None:
                        messages.append({"role": "user", "content": inject})
                    if stop:
                        return
                    continue

            # Execute
            try:
                result = await self._execute_single_tool(name, args)
            except Exception as e:
                result = f"Error: {e}"

            processed_ids.add(call_id)
            if self.cb is not None:
                self.cb.on_tool_complete(call_id, str(result))

            messages.append({
                "role": "tool",
                "tool_call_id": call_id,
                "name": name,
                "content": str(result),
            })

    def _needs_confirmation(self, tool_name: str) -> bool:
        perm = TOOL_PERMISSIONS.get(tool_name, "r")
        return perm not in self.config.permissions

    # -- Hooks (override in subclasses) ---------------------------------------

    async def _call_llm(self, messages: list, model: str, tools: list, num_ctx: int) -> Any:
        """Hook: perform the actual LLM call. Override to use a different call path."""
        return await self.llm.chat(
            messages, model=model, tools=tools, options={"num_ctx": num_ctx}
        )

    async def _execute_single_tool(self, name: str, args: dict) -> Any:
        """Hook: execute one tool call. Override to run in a thread pool, etc."""
        return self.registry.execute(name, args)

    async def _on_response_content(self, content: str, tool_calls: Optional[list]) -> None:
        """Hook: called after LLM response parsed. Override for content post-processing."""
        if not tool_calls and self.cb is not None and content:
            self.cb.on_assistant_content(content)

    async def _after_tool_batch(self) -> None:
        """Hook: called after a batch of tool calls completes. Override for cleanup."""

    async def _on_deny(
        self, confirm: Any, tool_calls: list, current_tc: Any, processed_ids: set, messages: list
    ) -> tuple[bool, Optional[str]]:
        """Hook: called when a tool is denied. Return (stop_loop, inject_message).

        Default: do nothing (continue processing remaining tools).
        Override to handle 'instruct' action (TUI) or similar.
        """
        return False, None

    async def _parse_custom_tool_calls(self, content: str) -> Optional[list]:
        """Hook: parse XML/JSON tool calls from text content. Returns None by default."""
        return None

    async def _execute_custom_tool_calls(self, calls: list, messages: list) -> None:
        """Hook: execute custom (XML/JSON) tool calls. No-op by default."""

    # -- Checkpoint -----------------------------------------------------------

    async def _handle_checkpoint(self, messages: list) -> bool:
        """Trigger checkpoint via memory_manager or checkpoint_manager.

        Returns True if loop should reset and continue.
        """
        if self.mm is not None:
            try:
                self.mm.create_checkpoint(messages)
            except Exception:
                pass

        if self.cm is not None:
            try:
                # Restore if checkpoint exists
                if self.cm.has_saved_checkpoint():
                    self.mm and self.mm.restore_from_checkpoint()
                    restore_msg = (
                        self.mm.build_quick_restore_message()
                        if self.mm
                        else "[SYSTEM: Context compacted. Continuing...]"
                    )
                    system_msg = messages[0] if messages and messages[0].get("role") == "system" else None
                    messages.clear()
                    if system_msg:
                        messages.append(system_msg)
                    messages.append({"role": "user", "content": restore_msg})
                    if self.cb is not None:
                        self.cb.on_system_message("Checkpoint saved — context compacted. Continuing...")
                    return True

                self.cm.save_checkpoint(_build_summary(messages))
                if self.cb is not None:
                    self.cb.on_system_message("Checkpoint saved.")
            except Exception:
                pass

        return False


# -- Response parsing helpers -------------------------------------------------


def _parse_response(response: Any) -> tuple[str, list | None, int]:
    """Extract (content, tool_calls, total_tokens) from various response formats."""
    # Format 1: FakeLLMResponse with direct attributes (.content, .tool_calls, .total_tokens)
    if hasattr(response, "total_tokens") and not hasattr(response, "choices"):
        content = getattr(response, "content", "") or ""
        tool_calls = getattr(response, "tool_calls", None)
        total_tokens = getattr(response, "total_tokens", 0) or 0
        return content, tool_calls if tool_calls else None, total_tokens

    # Format 2: OpenAI-style response with .choices[0].message
    if hasattr(response, "choices"):
        message = response.choices[0].message
        content = getattr(message, "content", "") or ""
        tool_calls = getattr(message, "tool_calls", None)
        usage = getattr(response, "usage", None)
        total_tokens = getattr(usage, "total_tokens", 0) or 0 if usage else 0
        return content, tool_calls if tool_calls else None, total_tokens

    return "", None, 0


def _tc_name(tc: Any) -> str:
    """Get tool name from FakeToolCall (.name) or OpenAI (.function.name)."""
    if hasattr(tc, "function"):
        name = tc.function.name
        if isinstance(name, str):
            return name
        # MagicMock(name="write_file") doesn't set .name as attribute.
        # The actual function name is stored in the mock's _mock_name.
        mock_name = getattr(tc.function, "_mock_name", None)
        if mock_name and isinstance(mock_name, str):
            return mock_name
        return str(name)
    raw = getattr(tc, "name", "unknown")
    return raw if isinstance(raw, str) else str(raw)


def _tc_arguments(tc: Any) -> dict:
    """Get tool arguments from FakeToolCall (.arguments) or OpenAI (.function.arguments)."""
    if hasattr(tc, "function"):
        args = tc.function.arguments
        if isinstance(args, str):
            try:
                return json.loads(args)
            except Exception:
                return {}
        return args or {}
    args = getattr(tc, "arguments", {})
    if isinstance(args, str):
        try:
            return json.loads(args)
        except Exception:
            return {}
    return args or {}


def _tc_id(tc: Any) -> str:
    """Get tool call id."""
    return getattr(tc, "id", "tc-unknown")


def _serialize_tool_calls(tool_calls: list) -> list[dict]:
    """Serialize tool calls for the message history."""
    result = []
    for tc in tool_calls:
        if hasattr(tc, "function"):
            result.append({
                "id": _tc_id(tc),
                "type": getattr(tc, "type", "function"),
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            })
        else:
            result.append({
                "id": _tc_id(tc),
                "type": "function",
                "function": {
                    "name": _tc_name(tc),
                    "arguments": json.dumps(_tc_arguments(tc)),
                },
            })
    return result


def _build_summary(messages: list) -> str:
    summary_parts = []
    for msg in messages[-10:]:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if content:
            summary_parts.append(f"[{role}] {str(content)[:200]}")
    return "\n".join(summary_parts)
