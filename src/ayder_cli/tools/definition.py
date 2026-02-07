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
    exposed_to_llm: bool = True

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
    ToolDefinition(
        name="get_project_structure",
        description="Generate a tree-style project structure summary.",
        description_template="Project structure will be displayed",
        parameters={
            "type": "object",
            "properties": {},
        },
        permission="r",
        exposed_to_llm=False,  # not in tools_schema sent to LLM
    ),
    # ---- File System (write) ----
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
    # ---- Shell (execute) ----
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
    # ---- Task Management ----
    ToolDefinition(
        name="create_task",
        description=(
            "Create a task saved as a markdown file. Use this when the user "
            "asks to create, add, or plan a task."
        ),
        description_template="Task TASK-XXX.md will be created in .ayder/tasks/",
        parameters={
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Short title for the task",
                },
                "description": {
                    "type": "string",
                    "description": "Detailed description of what the task involves",
                },
            },
            "required": ["title"],
        },
        permission="w",
        is_terminal=True,
    ),
    ToolDefinition(
        name="show_task",
        description=(
            "Show the details of a task by its ID number. Use this when the "
            "user asks to see or show a specific task."
        ),
        description_template="Task TASK-{task_id} will be displayed",
        parameters={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "integer",
                    "description": "The task number (e.g., 1 for TASK-001)",
                },
            },
            "required": ["task_id"],
        },
        permission="r",
        is_terminal=True,
    ),
    ToolDefinition(
        name="list_tasks",
        description="List all tasks in .ayder/tasks/ in a table format.",
        description_template="Tasks will be listed",
        parameters={
            "type": "object",
            "properties": {},
        },
        permission="r",
        is_terminal=True,
        exposed_to_llm=False,  # not in tools_schema sent to LLM
    ),
    ToolDefinition(
        name="implement_task",
        description=(
            "Implement a specific task, verify it, and set the status to done. "
            "Use this when the user asks to implement a specific task."
        ),
        description_template="Task TASK-{task_id} will be implemented",
        parameters={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "integer",
                    "description": (
                        "The task number to implement (e.g., 1 for TASK-001)"
                    ),
                },
            },
            "required": ["task_id"],
        },
        permission="w",
        is_terminal=True,
    ),
    ToolDefinition(
        name="implement_all_tasks",
        description=(
            "Implement all pending tasks one by one, verify them, and set "
            "their status to done. Use this when the user asks to implement "
            "all tasks."
        ),
        description_template="All pending tasks will be implemented",
        parameters={
            "type": "object",
            "properties": {},
        },
        permission="w",
        is_terminal=True,
    ),
)

# Lookup by name
TOOL_DEFINITIONS_BY_NAME: Dict[str, ToolDefinition] = {td.name: td for td in TOOL_DEFINITIONS}
