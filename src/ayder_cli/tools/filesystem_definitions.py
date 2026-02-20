"""
Tool definitions for filesystem operations.

Tools: list_files, read_file, write_file, replace_string, insert_line, delete_line, get_file_info
"""

from typing import Tuple

from .definition import ToolDefinition

# Shared file path aliases
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
        tags=("core",),
        func_ref="ayder_cli.tools.filesystem:list_files",
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
        tags=("core",),
        func_ref="ayder_cli.tools.filesystem:read_file",
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
    ToolDefinition(
        name="write_file",
        description=(
            "Write content to a file, overwriting it entirely. "
            "ONLY use this for new files or very short files (under ~50 lines). "
            "For existing files, prefer replace_string to avoid sending the full content. "
            "Embedding large content here is unreliable and wastes context."
        ),
        description_template="File {file_path} will be written",
        tags=("core",),
        func_ref="ayder_cli.tools.filesystem:write_file",
        parameters={
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "The path to the file to write",
                },
                "content": {
                    "type": "string",
                    "description": "The full content to write. Keep this small. For large or existing files use replace_string instead.",
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
        description=(
            "Replace a specific string in a file with a new string. "
            "PREFER this over write_file for any edit to an existing file. "
            "Works like a search/replace patch: provide a unique excerpt of the current content "
            "as old_string and the updated version as new_string. "
            "Make multiple calls to apply multiple changes. "
            "old_string must match the file exactly, including indentation."
        ),
        description_template="File {file_path} will be modified",
        tags=("core",),
        func_ref="ayder_cli.tools.filesystem:replace_string",
        parameters={
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "The path to the file to modify",
                },
                "old_string": {
                    "type": "string",
                    "description": "The exact string to find and replace (must be unique in the file and match indentation exactly)",
                },
                "new_string": {
                    "type": "string",
                    "description": "The new string to substitute in place of old_string",
                },
            },
            "required": ["file_path", "old_string", "new_string"],
        },
        permission="w",
        safe_mode_blocked=True,
        parameter_aliases=_FILE_PATH_ALIASES,
        path_parameters=("file_path",),
    ),
    # ---- File System (line editing) ----
    ToolDefinition(
        name="insert_line",
        description="Insert content at a specific line number in a file.",
        description_template="File {file_path} will be modified (insert at line {line_number})",
        tags=("core",),
        func_ref="ayder_cli.tools.filesystem:insert_line",
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
    ToolDefinition(
        name="delete_line",
        description="Delete a specific line from a file.",
        description_template="File {file_path} will be modified (delete line {line_number})",
        tags=("core",),
        func_ref="ayder_cli.tools.filesystem:delete_line",
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
        tags=("core",),
        func_ref="ayder_cli.tools.filesystem:get_file_info",
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
)