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

    # ---- implementation reference ----
    func_ref: str = ""  # "module.path:function_name" for auto-registration

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
# All tool definitions
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
        func_ref="ayder_cli.tools.impl:list_files",
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
        func_ref="ayder_cli.tools.impl:read_file",
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
        func_ref="ayder_cli.tools.impl:write_file",
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
        func_ref="ayder_cli.tools.impl:replace_string",
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
        func_ref="ayder_cli.tools.impl:search_codebase",
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
                "output_format": {
                    "type": "string",
                    "enum": ["full", "files_only", "count"],
                    "description": "Output format: 'full' (default, matching lines), 'files_only' (file paths only), 'count' (match counts per file)",
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
        func_ref="ayder_cli.tools.impl:get_project_structure",
        parameters={
            "type": "object",
            "properties": {
                "max_depth": {
                    "type": "integer",
                    "description": "Maximum directory depth to display (default: 3)",
                },
            },
        },
        permission="r",
    ),
    # ---- File System (line editing) ----
    # insert_line
    ToolDefinition(
        name="insert_line",
        description="Insert content at a specific line number in a file.",
        description_template="File {file_path} will be modified (insert at line {line_number})",
        func_ref="ayder_cli.tools.impl:insert_line",
        parameters={
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "The path to the file to modify",
                },
                "line_number": {
                    "type": "integer",
                    "description": "The line number to insert at (1-based). Lines at and after this position shift down.",
                },
                "content": {
                    "type": "string",
                    "description": "The content to insert",
                },
            },
            "required": ["file_path", "line_number", "content"],
        },
        permission="w",
        safe_mode_blocked=True,
        parameter_aliases=_FILE_PATH_ALIASES,
        path_parameters=("file_path",),
    ),
    # delete_line
    ToolDefinition(
        name="delete_line",
        description="Delete a specific line from a file.",
        description_template="File {file_path} will be modified (delete line {line_number})",
        func_ref="ayder_cli.tools.impl:delete_line",
        parameters={
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "The path to the file to modify",
                },
                "line_number": {
                    "type": "integer",
                    "description": "The line number to delete (1-based).",
                },
            },
            "required": ["file_path", "line_number"],
        },
        permission="w",
        safe_mode_blocked=True,
        parameter_aliases=_FILE_PATH_ALIASES,
        path_parameters=("file_path",),
    ),
    # ---- File Info (read) ----
    ToolDefinition(
        name="get_file_info",
        description="Get metadata about a file (size, line count, type).",
        description_template="File info for {file_path} will be retrieved",
        func_ref="ayder_cli.tools.impl:get_file_info",
        parameters={
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "The path to the file to inspect",
                },
            },
            "required": ["file_path"],
        },
        permission="r",
        parameter_aliases=_FILE_PATH_ALIASES,
        path_parameters=("file_path",),
    ),
    # ---- Notes ----
    ToolDefinition(
        name="create_note",
        description="Create a markdown note in .ayder/notes/ for investigation findings or documentation.",
        description_template="Note '{title}' will be created",
        func_ref="ayder_cli.notes:create_note",
        parameters={
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "The title of the note",
                },
                "content": {
                    "type": "string",
                    "description": "The markdown content of the note",
                },
                "tags": {
                    "type": "string",
                    "description": "Comma-separated tags (e.g., 'bug,security,frontend')",
                },
            },
            "required": ["title", "content"],
        },
        permission="w",
        safe_mode_blocked=False,
    ),
    # ---- Memory ----
    ToolDefinition(
        name="save_memory",
        description="Save a piece of context or insight to persistent cross-session memory.",
        description_template="Memory will be saved (category: {category})",
        func_ref="ayder_cli.memory:save_memory",
        parameters={
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The content to remember",
                },
                "category": {
                    "type": "string",
                    "description": "Category for organization (e.g., 'architecture', 'decisions', 'bugs')",
                },
                "tags": {
                    "type": "string",
                    "description": "Comma-separated tags for filtering",
                },
            },
            "required": ["content"],
        },
        permission="w",
        safe_mode_blocked=False,
    ),
    ToolDefinition(
        name="load_memory",
        description="Load saved memories from persistent cross-session storage.",
        description_template="Memories will be loaded",
        func_ref="ayder_cli.memory:load_memory",
        parameters={
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Filter by category",
                },
                "query": {
                    "type": "string",
                    "description": "Search query to filter memories by content",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of memories to return (default: 10)",
                },
            },
        },
        permission="r",
    ),
    # ---- Shell (execute) ----
    # run_shell_command
    ToolDefinition(
        name="run_shell_command",
        description="Execute a shell command.",
        description_template="Command `{command}` will be executed",
        func_ref="ayder_cli.tools.impl:run_shell_command",
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
    # ---- Background Processes ----
    ToolDefinition(
        name="run_background_process",
        description="Start a long-running command in the background (servers, watchers, builds).",
        description_template="Background command `{command}` will be started",
        func_ref="ayder_cli.process_manager:run_background_process",
        parameters={
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The command to run in the background (e.g., 'npm run dev', 'python -m http.server')",
                },
            },
            "required": ["command"],
        },
        permission="x",
        safe_mode_blocked=True,
    ),
    ToolDefinition(
        name="get_background_output",
        description="Get recent stdout/stderr output from a background process.",
        description_template="Output for background process {process_id} will be retrieved",
        func_ref="ayder_cli.process_manager:get_background_output",
        parameters={
            "type": "object",
            "properties": {
                "process_id": {
                    "type": "integer",
                    "description": "The ID of the background process",
                },
                "tail": {
                    "type": "integer",
                    "description": "Number of recent lines to return (default: 50)",
                },
            },
            "required": ["process_id"],
        },
        permission="r",
    ),
    ToolDefinition(
        name="kill_background_process",
        description="Kill a running background process.",
        description_template="Background process {process_id} will be killed",
        func_ref="ayder_cli.process_manager:kill_background_process",
        parameters={
            "type": "object",
            "properties": {
                "process_id": {
                    "type": "integer",
                    "description": "The ID of the background process to kill",
                },
            },
            "required": ["process_id"],
        },
        permission="x",
        safe_mode_blocked=True,
    ),
    ToolDefinition(
        name="list_background_processes",
        description="List all background processes and their status.",
        description_template="Background processes will be listed",
        func_ref="ayder_cli.process_manager:list_background_processes",
        parameters={
            "type": "object",
            "properties": {},
        },
        permission="r",
    ),
    # ---- Task Management ----
    ToolDefinition(
        name="list_tasks",
        description="List task files in .ayder/tasks/ directory, filtered by status (default: pending tasks only).",
        description_template="Task files will be listed",
        func_ref="ayder_cli.tasks:list_tasks",
        parameters={
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "description": "Filter by status: 'pending' (default), 'done', or 'all'",
                    "enum": ["pending", "done", "all"],
                },
            },
        },
        permission="r",
    ),
    ToolDefinition(
        name="show_task",
        description="Read and return the contents of a task file. Accepts relative path, filename, task ID, or slug.",
        description_template="Task `{identifier}` will be displayed",
        func_ref="ayder_cli.tasks:show_task",
        parameters={
            "type": "object",
            "properties": {
                "identifier": {
                    "type": "string",
                    "description": "Task identifier: relative path (e.g., '.ayder/tasks/TASK-001-add-auth.md'), filename (e.g., 'TASK-001-add-auth.md'), task ID (e.g., '001' or 'TASK-001'), or slug (e.g., 'add-auth')",
                },
            },
            "required": ["identifier"],
        },
        permission="r",
    ),

)

# Lookup by name
TOOL_DEFINITIONS_BY_NAME: Dict[str, ToolDefinition] = {td.name: td for td in TOOL_DEFINITIONS}
