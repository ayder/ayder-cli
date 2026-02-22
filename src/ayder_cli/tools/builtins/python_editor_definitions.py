"""
Tool definition for the unified python_editor tool.

Provides CST-based structural Python code manipulation.
Uses libcst for CST-based code manipulation.
"""

from typing import Tuple

from ..definition import ToolDefinition

TOOL_DEFINITIONS: Tuple[ToolDefinition, ...] = (
    ToolDefinition(
        name="python_editor",
        description=(
            "Structural Python code editor using Concrete Syntax Tree (CST). "
            "Preserves indentation and comments during transformations. "
            "Methods: get, list_all, replace, delete, rename, add_decorator, "
            "add_import, verify. Pass method-specific arguments via the "
            "'params' JSON string."
        ),
        description_template="Python editor: {method} on {file_path}",
        tags=("core",),
        func_ref="ayder_cli.tools.builtins.python_editor:python_editor",
        parameters={
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the Python file to edit.",
                },
                "method": {
                    "type": "string",
                    "enum": [
                        "get",
                        "list_all",
                        "replace",
                        "delete",
                        "rename",
                        "add_decorator",
                        "add_import",
                        "verify",
                    ],
                    "description": "The operation to perform.",
                },
                "params": {
                    "type": "string",
                    "description": (
                        "JSON object with method-specific parameters. "
                        'get: {"target_name": "symbol"}, '
                        'replace: {"target_name": "symbol", "new_code": "def ..."}, '
                        'delete: {"target_name": "symbol"}, '
                        'rename: {"old_name": "old", "new_name": "new"}, '
                        'add_decorator: {"target_name": "symbol", "decorator": "cache"}, '
                        'add_import: {"module": "os", "name": "path"}, '
                        "list_all/verify: {} or omit."
                    ),
                },
            },
            "required": ["file_path", "method"],
        },
        permission="w",
        path_parameters=("file_path",),
        parameter_aliases=(
            ("path", "file_path"),
            ("filepath", "file_path"),
        ),
    ),
)
