"""File system tools module (backwards compatibility).

This module re-exports all tool functionality from the tools package.
New code should import from ayder_cli.tools directly.
"""

# Re-export everything from the tools package for backwards compatibility
from ayder_cli.tools.schemas import tools_schema
from ayder_cli.tools.registry import (
    ToolRegistry,
    normalize_tool_arguments,
    validate_tool_call,
    PARAMETER_ALIASES,
    PATH_PARAMETERS,
    execute_tool_call,
)
from ayder_cli.tools.impl import (
    list_files,
    read_file,
    write_file,
    replace_string,
    run_shell_command,
    get_project_structure,
    search_codebase,
    get_project_context,
)
from ayder_cli.path_context import ProjectContext

# Re-export task management functions for backwards compatibility
from ayder_cli.tasks import (
    create_task,
    show_task,
    implement_task,
    implement_all_tasks,
)

__all__ = [
    "tools_schema",
    "ToolRegistry",
    "normalize_tool_arguments",
    "validate_tool_call",
    "PARAMETER_ALIASES",
    "PATH_PARAMETERS",
    "execute_tool_call",
    "list_files",
    "read_file",
    "write_file",
    "replace_string",
    "run_shell_command",
    "get_project_structure",
    "search_codebase",
    "create_task",
    "show_task",
    "implement_task",
    "implement_all_tasks",
    "ProjectContext",
    "get_project_context",
]