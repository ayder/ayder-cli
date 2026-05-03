"""
Tool definitions for filesystem operations.

Tools: file_explorer, read_file, file_editor
"""

from typing import Tuple

from ..definition import ToolDefinition

# Shared file path aliases
_FILE_PATH_ALIASES = (
    ("path", "file_path"),
    ("absolute_path", "file_path"),
    ("filepath", "file_path"),
)

TOOL_DEFINITIONS: Tuple[ToolDefinition, ...] = (
    ToolDefinition(
        name="file_explorer",
        description="List files in a directory or get metadata for a specific file.",
        description_template="Exploring path {path}",
        tags=("core",),
        func_ref="ayder_cli.tools.builtins.filesystem:file_explorer",
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The directory to list or file to inspect (default: '.')",
                    "default": ".",
                },
            },
        },
        permission="r",
        parameter_aliases=(
            ("dir", "path"),
            ("directory", "path"),
            ("folder", "path"),
            ("file_path", "path"),
        ),
        path_parameters=("path",),
    ),
    ToolDefinition(
        name="read_file",
        description=(
            "Read the contents of a file. Output uses '<line_no>: <text>' "
            "formatting. Without a range, returns up to the first 2000 lines; "
            "if the file is longer, the result includes a footer naming the "
            "total line count and the exact follow-up call to fetch the next "
            "page (call again with start_line set to the next line). Pass "
            "explicit start_line / end_line (1-based, inclusive) to read a "
            "specific slice."
        ),
        description_template="File {file_path} will be read",
        tags=("core",),
        func_ref="ayder_cli.tools.builtins.filesystem:read_file",
        parameters={
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the file to read",
                },
                "start_line": {
                    "type": "integer",
                    "description": "Line number to start reading from (1-based, inclusive)",
                },
                "end_line": {
                    "type": "integer",
                    "description": "Line number to stop reading at (1-based, inclusive)",
                },
            },
            "required": ["file_path"],
        },
        permission="r",
        parameter_aliases=_FILE_PATH_ALIASES,
        path_parameters=("file_path",),
        # read_file paginates internally; the chat-loop's head+tail truncation
        # would silently corrupt the deliberately-bounded page payload.
        max_result_chars=0,
    ),
    ToolDefinition(
        name="file_editor",
        description=(
            "Modify files. Supports operations: 'write' (overwrite entirely, for new/small files), "
            "'replace' (replace exact string match), 'insert' (add content at line), and 'delete' (remove line)."
        ),
        description_template="File {file_path} will be modified ({operation})",
        tags=("core",),
        func_ref="ayder_cli.tools.builtins.filesystem:file_editor",
        parameters={
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the file to modify",
                },
                "operation": {
                    "type": "string",
                    "enum": ["write", "replace", "insert", "delete"],
                    "description": "The edit operation to perform",
                },
                "content": {
                    "type": "string",
                    "description": "Content for 'write' or 'insert' operations",
                },
                "old_string": {
                    "type": "string",
                    "description": "Exact string to find for 'replace' operation",
                },
                "new_string": {
                    "type": "string",
                    "description": "New string to substitute for 'replace' operation",
                },
                "line_number": {
                    "type": "integer",
                    "description": "Line number (1-based) for 'insert' or 'delete' operations",
                },
            },
            "required": ["file_path", "operation"],
        },
        permission="w",
        safe_mode_blocked=True,
        parameter_aliases=_FILE_PATH_ALIASES,
        path_parameters=("file_path",),
    ),
)