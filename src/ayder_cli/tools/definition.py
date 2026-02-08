"""
Schema-driven ToolDefinition — single source of truth for all tool metadata.

Every tool's schema, permissions, aliases, path parameters, terminal/safe-mode
flags, and description template live in one frozen dataclass.  All existing
constants (tools_schema, TOOL_PERMISSIONS, PARAMETER_ALIASES, PATH_PARAMETERS,
TERMINAL_TOOLS) are generated from TOOL_DEFINITIONS at import time.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, Optional, Tuple


@dataclass(frozen=True)
class ToolDefinition:
    """Immutable definition of a single tool."""

    # ---- identity ----
    name: str
    description: str
    parameters: Dict[str, Any]  # OpenAI "parameters" object

    # ---- permission & flags ----
    permission: str = "r"  # "r", "w", or "x"
    is_terminal: bool = False
    safe_mode_blocked: bool = False


    # ---- UI ----
    description_template: Optional[str] = None

    # ---- parameter normalisation helpers ----
    parameter_aliases: Tuple[Tuple[str, str], ...] = ()  # ((alias, canonical), ...)
    path_parameters: Tuple[str, ...] = ()  # parameter names resolved via ProjectContext

    def to_openai_schema(self) -> Dict[str, Any]:
        """Return the OpenAI function-calling dict for this tool."""
        func: Dict[str, Any] = {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }
        if self.description_template is not None:
            func["description_template"] = self.description_template
        return {"type": "function", "function": func}


# ---------------------------------------------------------------------------
# All 12 tool definitions
# ---------------------------------------------------------------------------

_FILE_PATH_ALIASES = (
    ("path", "file_path"),
    ("absolute_path", "file_path"),
    ("filepath", "file_path"),
)

TOOL_DEFINITIONS: Tuple[ToolDefinition, ...] = (
    # ---- File System (read) ----
    ToolDefinition(
        name="list_files",
        description="List files in a directory",
        description_template="Directory {directory} will be listed",
        parameters={
            "type": "object",
            "properties": {
                "directory": {
                    "type": "string",
                    "description": "The directory path (default: '.')",
                    "default": ".",
                },
            },
        },
        permission="r",

        parameter_aliases=(
            ("dir", "directory"),
            ("path", "directory"),
            ("folder", "directory"),
        ),
        path_parameters=("directory",),
    ),
    ToolDefinition(
        name="read_file",
        description="Read the contents of a file, optionally specifying a line range.",
        description_template="File {file_path} will be read",
        parameters={
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "The path to the file to read",
                },
                "start_line": {
                    "type": "integer",
                    "description": "The line number to start reading from (1-based).",
                },
                "end_line": {
                    "type": "integer",
                    "description": "The line number to stop reading at (1-based).",
                },
            },
            "required": ["file_path"],
        },
        permission="r",

        parameter_aliases=_FILE_PATH_ALIASES,
        path_parameters=("file_path",),
    ),
    # ---- File System (write) ----
    # write_file
    ToolDefinition(
        name="write_file",
        description="Write content to a file (overwrites entire file).",
        description_template="File {file_path} will be written",
        parameters={
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "The path to the file to write",
                },
                "content": {
                    "type": "string",
                    "description": "The content to write",
                },
            },
            "required": ["file_path", "content"],
        },
        permission="w",

        safe_mode_blocked=True,
        parameter_aliases=_FILE_PATH_ALIASES,
        path_parameters=("file_path",),
    ),
    # replace_string
    ToolDefinition(
        name="replace_string",
        description="Replace a specific string in a file with a new string.",
        description_template="File {file_path} will be modified",
        parameters={
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "The path to the file to modify",
                },
                "old_string": {
                    "type": "string",
                    "description": "The exact string to replace",
                },
                "new_string": {
                    "type": "string",
                    "description": "The new string to insert",
                },
            },
            "required": ["file_path", "old_string", "new_string"],
        },
        permission="w",

        safe_mode_blocked=True,
        parameter_aliases=_FILE_PATH_ALIASES,
        path_parameters=("file_path",),
    ),
    # ---- Search ----
    ToolDefinition(
        name="search_codebase",
        description=(
            "Search for a regex pattern across the codebase. Returns matching "
            "lines with file paths and line numbers. Use this to locate code "
            "before reading files."
        ),
        description_template="Codebase will be searched for pattern '{pattern}'",
        parameters={
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": (
                        "The regex pattern to search for "
                        "(e.g., 'def read_file', 'class.*Test', 'TODO.*bug')"
                    ),
                },
                "file_pattern": {
                    "type": "string",
                    "description": (
                        "Optional file glob pattern to limit search "
                        "(e.g., '*.py', 'src/**/*.js')"
                    ),
                },
                "case_sensitive": {
                    "type": "boolean",
                    "description": "Whether the search is case-sensitive (default: true)",
                },
                "context_lines": {
                    "type": "integer",
                    "description": (
                        "Number of context lines to show before/after each match (default: 0)"
                    ),
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of matches to return (default: 50)",
                },
                "directory": {
                    "type": "string",
                    "description": "Root directory to search (default: '.')",
                },
            },
            "required": ["pattern"],
        },
        permission="r",

        path_parameters=("directory",),
    ),
    # get_project_structure
    ToolDefinition(
        name="get_project_structure",
        description="Generate a tree-style project structure summary.",
        description_template="Project structure will be displayed",
        parameters={
            "type": "object",
            "properties": {},
        },
        permission="r",

    ),
    # ---- Shell (execute) ----
    # run_shell_command
    ToolDefinition(
        name="run_shell_command",
        description="Execute a shell command.",
        description_template="Command `{command}` will be executed",
        parameters={
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": (
                        "The command to execute (e.g., 'ls -la', 'python test.py')"
                    ),
                },
            },
            "required": ["command"],
        },
        permission="x",

        safe_mode_blocked=True,
    ),

)

# Lookup by name
TOOL_DEFINITIONS_BY_NAME: Dict[str, ToolDefinition] = {td.name: td for td in TOOL_DEFINITIONS}
