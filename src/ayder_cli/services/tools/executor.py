import json
from typing import List, Set, Dict, Any, Optional, Tuple

from ayder_cli.tools.registry import ToolRegistry
from ayder_cli.tools.schemas import TOOL_PERMISSIONS
from ayder_cli.tools.definition import TOOL_DEFINITIONS
from ayder_cli.tools import prepare_new_content
from ayder_cli.core.result import ToolSuccess
from ayder_cli.ui import (
    confirm_tool_call,
    describe_tool_action,
    print_tool_result,
    print_file_content,
    confirm_with_diff,
    print_tool_skipped
)

# Tools that end the agentic loop after execution (generated from ToolDefinitions)
TERMINAL_TOOLS = frozenset(td.name for td in TOOL_DEFINITIONS if td.is_terminal)


class ToolExecutor:
    """
    Handles the execution of tool calls, including validation, user confirmation,
    and interaction with the ToolRegistry.
    """

    def __init__(self, tool_registry: ToolRegistry, terminal_tools: Set[str] = None):
        """
        Initialize the ToolExecutor.

        Args:
            tool_registry: Registry to execute tools.
            terminal_tools: Set of tool names that should terminate the agent loop.
                            Defaults to TERMINAL_TOOLS if None.
        """
        self.tool_registry = tool_registry
        self.terminal_tools = terminal_tools if terminal_tools is not None else TERMINAL_TOOLS

    def execute_tool_calls(self, tool_calls: List[Any], session: Any, granted_permissions: Set[str] = None, verbose: bool = False) -> bool:
        """
        Execute a list of OpenAI tool calls.

        Args:
            tool_calls: List of tool call objects from OpenAI response.
            session: ChatSession object to append messages to.
            granted_permissions: Set of granted permission categories.
            verbose: Whether to print verbose output.

        Returns:
            True if a terminal tool was hit, False otherwise.
        """
        if granted_permissions is None:
            granted_permissions = set()

        for tc in tool_calls:
            result_msg = self._handle_tool_call(tc, granted_permissions, verbose)
            if result_msg is None:
                # Tool was declined
                return True
            
            session.append_raw(result_msg)
            
            # Check if terminal tool
            if tc.function.name in self.terminal_tools:
                return True
        
        return False

    def execute_custom_calls(self, custom_calls: List[Dict[str, Any]], session: Any, granted_permissions: Set[str] = None, verbose: bool = False) -> bool:
        """
        Execute a list of custom parsed tool calls (XML).

        Args:
            custom_calls: List of custom parsed tool calls.
            session: ChatSession object to append messages to.
            granted_permissions: Set of granted permission categories.
            verbose: Whether to print verbose output.

        Returns:
            True if a terminal tool was hit, False otherwise.
        """
        if granted_permissions is None:
            granted_permissions = set()

        for call in custom_calls:
            fname = call['name']
            fargs = call['arguments']

            outcome, value = self._execute_single_call(fname, fargs, granted_permissions, verbose)

            if outcome == "error":
                session.add_message("user", f"Validation Error for tool '{fname}': {value}")
                return True
            if outcome == "declined":
                return True
            # success
            session.add_message("user", f"Tool '{fname}' execution result: {value}")
            if fname in self.terminal_tools:
                return True

        return False

    def _execute_single_call(
        self, tool_name: str, raw_args: dict,
        granted_permissions: Set[str], verbose: bool
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

        is_valid, error_msg = self.tool_registry.validate_args(tool_name, normalized)
        if not is_valid:
            return ("error", error_msg)

        description = describe_tool_action(tool_name, normalized)

        # Check if tool is auto-approved by permission flags
        tool_perm = TOOL_PERMISSIONS.get(tool_name, "x")
        auto_approved = tool_perm in granted_permissions

        if auto_approved:
            confirmed = True
        elif tool_name in ("write_file", "replace_string", "insert_line", "delete_line"):
            file_path = normalized.get("file_path", "")
            new_content = prepare_new_content(tool_name, normalized, self.tool_registry.project_ctx)
            confirmed = confirm_with_diff(file_path, new_content, description)
        else:
            confirmed = confirm_tool_call(description)

        if not confirmed:
            print_tool_skipped()
            return ("declined", None)

        result = self.tool_registry.execute(tool_name, normalized)
        print_tool_result(result)

        if verbose and tool_name == "write_file" and isinstance(result, ToolSuccess):
            print_file_content(normalized.get("file_path", ""))

        return ("success", str(result))

    def _handle_tool_call(self, tool_call: Any, granted_permissions: Set[str], verbose: bool) -> Optional[Dict[str, Any]]:
        """
        Handle a single OpenAI-format tool call. Thin wrapper around _execute_single_call.

        Returns:
            Result message dict for the conversation, or None if declined.
        """
        fname = tool_call.function.name
        fargs = tool_call.function.arguments
        parsed = json.loads(fargs) if isinstance(fargs, str) else fargs

        outcome, value = self._execute_single_call(fname, parsed, granted_permissions, verbose)

        if outcome == "declined":
            return None
        # Both "success" and "error" return a tool message
        return {
            "role": "tool",
            "tool_call_id": tool_call.id,
            "name": fname,
            "content": value if outcome == "success" else f"Validation Error: {value}",
        }
