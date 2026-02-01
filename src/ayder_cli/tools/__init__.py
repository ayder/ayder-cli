"""Tools package for ayder-cli."""

from ayder_cli.tools.schemas import tools_schema
from ayder_cli.tools.registry import (
    ToolRegistry,
    normalize_tool_arguments,
    validate_tool_call,
    PARAMETER_ALIASES,
    PATH_PARAMETERS,
    execute_tool_call,
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

__all__ = [
    # Schemas
    "tools_schema",
    # Registry
    "ToolRegistry",
    "create_default_registry",
    "normalize_tool_arguments",
    "validate_tool_call",
    "PARAMETER_ALIASES",
    "PATH_PARAMETERS",
    "execute_tool_call",
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
]
