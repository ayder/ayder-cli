"""Tools package for ayder-cli."""

from ayder_cli.tools.definition import (
    ToolDefinition,
    TOOL_DEFINITIONS,
    TOOL_DEFINITIONS_BY_NAME,
)
from ayder_cli.tools.schemas import tools_schema, TOOL_PERMISSIONS
from ayder_cli.tools.registry import (
    ToolRegistry,
    create_default_registry,
    normalize_tool_arguments,   # deprecated alias — use normalize_arguments
)
from ayder_cli.tools.normalization import normalize_arguments, PARAMETER_ALIASES, PATH_PARAMETERS
from ayder_cli.tools.hooks import (
    HookManager,
    ToolExecutionResult,
    ToolExecutionStatus,
    MiddlewareFunc,
    PreExecuteCallback,
    PostExecuteCallback,
)
from ayder_cli.tools.utils import prepare_new_content
from ayder_cli.core.result import ToolSuccess, ToolError, ToolResult

__all__ = [
    # Definitions
    "ToolDefinition",
    "TOOL_DEFINITIONS",
    "TOOL_DEFINITIONS_BY_NAME",
    # Schemas
    "tools_schema",
    "TOOL_PERMISSIONS",
    # Registry
    "ToolRegistry",
    "create_default_registry",
    # Normalization
    "normalize_arguments",
    "normalize_tool_arguments",     # deprecated alias
    "PARAMETER_ALIASES",
    "PATH_PARAMETERS",
    # Hooks
    "HookManager",
    "ToolExecutionResult",
    "ToolExecutionStatus",
    "MiddlewareFunc",
    "PreExecuteCallback",
    "PostExecuteCallback",
    # Utils
    "prepare_new_content",
    # Result types
    "ToolSuccess",
    "ToolError",
    "ToolResult",
]
