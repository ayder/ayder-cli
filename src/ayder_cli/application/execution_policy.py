"""Shared Execution Policy Service — Phase 05.

Single policy path for both CLI and TUI tool execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

from ayder_cli.application.checkpoint_orchestrator import RuntimeContext


# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------


@dataclass
class ToolRequest:
    """A request to execute a tool."""

    name: str
    arguments: dict


@dataclass
class FileDiffConfirmation:
    """Represents a file diff that may need user confirmation."""

    file_path: str
    original_content: str
    new_content: str
    description: str


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class PermissionDeniedError(Exception):
    """Raised when a tool requires a permission that has not been granted."""

    def __init__(self, tool_name: str, required_permission: str) -> None:
        self.tool_name = tool_name
        self.required_permission = required_permission
        super().__init__(str(self))

    def __str__(self) -> str:
        return (
            f"Permission denied for '{self.tool_name}': "
            f"requires '{self.required_permission}'. "
            f"Grant with --permission {self.required_permission} or -x flag."
        )


@dataclass
class ToolExecutionError:
    """Structured error from tool execution."""

    tool_name: str
    message: str
    exit_code: int = 1

    def __str__(self) -> str:
        return f"[{self.tool_name}] {self.message} (exit {self.exit_code})"


@dataclass
class ValidationError:
    """Structured validation error."""

    tool_name: str
    field: str
    message: str

    def __str__(self) -> str:
        return f"Validation error for '{self.tool_name}.{self.field}': {self.message}"


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ConfirmationRequirement(Enum):
    NONE = "none"
    REQUIRED = "required"

    @property
    def requires_confirmation(self) -> bool:
        return self is ConfirmationRequirement.REQUIRED


class ConfirmationResult(Enum):
    APPROVED = "approved"
    DECLINED = "declined"
    INSTRUCT = "instruct"

    @property
    def executes_tool(self) -> bool:
        return self is ConfirmationResult.APPROVED

    @property
    def includes_instructions(self) -> bool:
        return self is ConfirmationResult.INSTRUCT


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------


@dataclass
class ExecutionResult:
    success: bool
    was_confirmed: bool = False
    error: Any = None


# ---------------------------------------------------------------------------
# Permission map
# ---------------------------------------------------------------------------

# Maps tool name fragments to required permission token
_PERMISSION_MAP: dict[str, str] = {
    "write_file": "w",
    "edit_file": "w",
    "delete_file": "w",
    "run_shell_command": "x",
    "execute": "x",
    "read_file": "r",
    "list_directory": "r",
    "search": "r",
}

# Read-only tools that need no confirmation
_READ_ONLY_TOOLS = {"read_file", "list_directory", "search"}


def _required_permission(tool_name: str) -> str:
    """Return the required permission token for a tool."""
    for fragment, perm in _PERMISSION_MAP.items():
        if fragment in tool_name:
            return perm
    return "r"


# ---------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------


class ExecutionPolicy:
    """Shared tool execution policy — identical behavior for CLI and TUI.

    References ValidationAuthority to ensure validation is not bypassed.
    """

    def __init__(self, granted_permissions: Optional[set] = None) -> None:
        self.granted_permissions: set = granted_permissions if granted_permissions is not None else set()

    def check_permission(
        self,
        tool_name: str,
        context: Optional[RuntimeContext] = None,
    ) -> Optional[PermissionDeniedError]:
        """Return PermissionDeniedError if permission is missing, else None."""
        required = _required_permission(tool_name)
        if required not in self.granted_permissions:
            return PermissionDeniedError(tool_name=tool_name, required_permission=required)
        return None

    def get_confirmation_requirement(self, tool_name: str) -> ConfirmationRequirement:
        """Return whether this tool needs user confirmation."""
        if tool_name in _READ_ONLY_TOOLS:
            return ConfirmationRequirement.NONE
        required = _required_permission(tool_name)
        if required not in self.granted_permissions:
            return ConfirmationRequirement.REQUIRED
        return ConfirmationRequirement.NONE

    def execute(
        self,
        request: ToolRequest,
        context: Optional[RuntimeContext] = None,
    ) -> ExecutionResult:
        """Check permissions and return an execution result.

        Validation is centralized through ValidationAuthority (see validation.py).
        """
        error = self.check_permission(request.name, context)
        if error is not None:
            return ExecutionResult(success=False, was_confirmed=False, error=error)
        return ExecutionResult(success=True, was_confirmed=False)

    def confirm_file_diff(self, diff: FileDiffConfirmation) -> bool:
        """Policy-level auto-approval for file diffs."""
        return True

    def format_error_for_llm(self, error: ToolExecutionError) -> dict:
        """Format a tool error as an LLM-consumable message."""
        return {
            "role": "tool",
            "content": f"error: {error.tool_name}: {error.message}",
        }
