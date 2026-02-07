"""Tools package for ayder-cli."""

from ayder_cli.tools.definition import ToolDefinition, TOOL_DEFINITIONS, TOOL_DEFINITIONS_BY_NAME
from ayder_cli.tools.schemas import tools_schema, TOOL_PERMISSIONS
from ayder_cli.tools.registry import (
    ToolRegistry,
    normalize_tool_arguments,
    validate_tool_call,
    PARAMETER_ALIASES,
    PATH_PARAMETERS,
    create_default_registry,
)
from ayder_cli.tools.impl import (
    list_files,
    read_file,
    write_file,
    replace_string,
    run_shell_command,
    get_project_structure,
    search_codebase,
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
    "normalize_tool_arguments",
    "validate_tool_call",
    "PARAMETER_ALIASES",
    "PATH_PARAMETERS",
    # Implementations
    "list_files",
    "read_file",
    "write_file",
    "replace_string",
    "run_shell_command",
    "get_project_structure",
    "search_codebase",
    # Utils
    "prepare_new_content",
    # Result types
    "ToolSuccess",
    "ToolError",
    "ToolResult",
]
