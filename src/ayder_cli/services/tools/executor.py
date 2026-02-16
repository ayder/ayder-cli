import json
from typing import List, Set, Dict, Any, Optional, Tuple

from ayder_cli.application.execution_policy import ExecutionPolicy, ToolRequest
from ayder_cli.tools.registry import ToolRegistry
from ayder_cli.tools.definition import TOOL_DEFINITIONS
from ayder_cli.tools import prepare_new_content
from ayder_cli.services.interactions import InteractionSink, ConfirmationPolicy

# Tools that end the agentic loop after execution (generated from ToolDefinitions)
TERMINAL_TOOLS = frozenset(td.name for td in TOOL_DEFINITIONS if td.is_terminal)

# File-modifying tools that use diff confirmation
_DIFF_TOOLS = frozenset({"write_file", "replace_string", "insert_line", "delete_line"})


class ToolExecutor:
    """
    Handles the execution of tool calls, including validation, user confirmation,
    and interaction with the ToolRegistry.
    """

    def __init__(
        self,
        tool_registry: ToolRegistry,
        terminal_tools: Set[str] | None = None,
        interaction_sink: InteractionSink | None = None,
        confirmation_policy: ConfirmationPolicy | None = None,
    ):
        """
        Initialize the ToolExecutor.

        Args:
            tool_registry: Registry to execute tools.
            terminal_tools: Set of tool names that should terminate the agent loop.
                            Defaults to TERMINAL_TOOLS if None.
            interaction_sink: Optional sink for tool event notifications.
            confirmation_policy: Optional policy for user confirmation flows.
        """
        self.tool_registry = tool_registry
        self.terminal_tools = (
            terminal_tools if terminal_tools is not None else TERMINAL_TOOLS
        )
        self.interaction_sink = interaction_sink
        self.confirmation_policy = confirmation_policy

    def execute_tool_calls(
        self,
        tool_calls: List[Any],
        session: Any,
        granted_permissions: Set[str] | None = None,
        verbose: bool = False,
    ) -> bool:
        """
        Execute a list of OpenAI tool calls.

        Returns:
            True if a terminal tool was hit, False otherwise.
        """
        if granted_permissions is None:
            granted_permissions = set()

        for tc in tool_calls:
            result_msg = self._handle_tool_call(tc, granted_permissions, verbose)
            if result_msg is None:
                return True

            session.append_raw(result_msg)

            if tc.function.name in self.terminal_tools:
                return True

        return False

    def execute_custom_calls(
        self,
        custom_calls: List[Dict[str, Any]],
        session: Any,
        granted_permissions: Set[str] | None = None,
        verbose: bool = False,
    ) -> bool:
        """
        Execute a list of custom parsed tool calls (XML).

        Returns:
            True if a terminal tool was hit, False otherwise.
        """
        if granted_permissions is None:
            granted_permissions = set()

        for call in custom_calls:
            fname = call["name"]
            fargs = call["arguments"]

            outcome, value = self._execute_single_call(
                fname, fargs, granted_permissions, verbose
            )

            if outcome == "error":
                session.add_message(
                    "user", f"Validation Error for tool '{fname}': {value}"
                )
                return True
            if outcome == "declined":
                return True
            session.add_message("user", f"Tool '{fname}' execution result: {value}")
            if fname in self.terminal_tools:
                return True

        return False

    def _execute_single_call(
        self,
        tool_name: str,
        raw_args: dict,
        granted_permissions: Set[str],
        verbose: bool,
    ) -> Tuple[str, Optional[str]]:
        """
        Unified tool execution: normalize → validate → confirm → execute.

        Returns:
            (outcome, value) tuple:
            - ("success", result_str) — tool executed successfully
            - ("error", error_msg) — validation/normalization error
            - ("declined", None) — user declined confirmation
        """
        try:
            normalized = self.tool_registry.normalize_args(tool_name, raw_args)
        except ValueError as e:
            return ("error", str(e))

        # Notify sink of tool call
        args_json = json.dumps(normalized, indent=2)
        if self.interaction_sink is not None:
            self.interaction_sink.on_tool_call(tool_name, args_json)

        # Check if tool is auto-approved via shared ExecutionPolicy
        policy = ExecutionPolicy(granted_permissions)
        auto_approved = policy.check_permission(tool_name) is None

        if auto_approved:
            confirmed = True
        elif self.confirmation_policy is not None:
            description = f"{tool_name}"
            # Primary gate: all tools require confirm_action
            confirmed = self.confirmation_policy.confirm_action(description)
            # Secondary gate for file-modifying tools: show diff
            if confirmed and tool_name in _DIFF_TOOLS:
                file_path = normalized.get("file_path", "")
                project_ctx = getattr(self.tool_registry, "project_ctx", None)
                new_content = (
                    prepare_new_content(tool_name, normalized, project_ctx)
                    if project_ctx is not None
                    else normalized.get("content", "")
                )
                confirmed = self.confirmation_policy.confirm_file_diff(
                    file_path, new_content, description
                )
        else:
            # No policy injected: auto-approve (caller must wire in policy for confirmation)
            confirmed = True

        if not confirmed:
            if self.interaction_sink is not None:
                self.interaction_sink.on_tool_skipped()
            return ("declined", None)

        # Route through shared execution policy — single call site for validate+permission+execute
        exec_result = policy.execute_with_registry(
            ToolRequest(tool_name, normalized), self.tool_registry
        )
        result_str = (exec_result.result or "") if exec_result.success else str(exec_result.error)

        if self.interaction_sink is not None:
            self.interaction_sink.on_tool_result(result_str)

        if verbose and tool_name == "write_file" and exec_result.success:
            file_path = normalized.get("file_path", "")
            if self.interaction_sink is not None:
                self.interaction_sink.on_file_preview(file_path)

        if not exec_result.success:
            return ("error", result_str)

        return ("success", result_str)

    def _handle_tool_call(
        self, tool_call: Any, granted_permissions: Set[str], verbose: bool
    ) -> Optional[Dict[str, Any]]:
        """
        Handle a single OpenAI-format tool call.

        Returns:
            Result message dict for the conversation, or None if declined.
        """
        fname = tool_call.function.name
        fargs = tool_call.function.arguments
        parsed = json.loads(fargs) if isinstance(fargs, str) else fargs

        outcome, value = self._execute_single_call(
            fname, parsed, granted_permissions, verbose
        )

        if outcome == "declined":
            return None
        return {
            "role": "tool",
            "tool_call_id": tool_call.id,
            "name": fname,
            "content": value if outcome == "success" else f"Validation Error: {value}",
        }
