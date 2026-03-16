"""
Tool definitions for search operations.

Tools: search_codebase, get_project_structure
"""

from typing import Tuple

from ..definition import ToolDefinition

TOOL_DEFINITIONS: Tuple[ToolDefinition, ...] = (
    ToolDefinition(
        name="search_codebase",
        tags=("core",),
        func_ref="ayder_cli.tools.builtins.search:search_codebase",
        description="Search files by name pattern or content regex.",
        description_template="Codebase will be searched for pattern '{pattern}'",
        parameters={
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Regex pattern to search for.",
                },
                "file_pattern": {
                    "type": "string",
                    "description": "Optional file glob filter.",
                },
                "case_sensitive": {
                    "type": "boolean",
                    "description": "Whether the search is case-sensitive (default: true)",
                },
                "context_lines": {
                    "type": "integer",
                    "description": "Context lines around match (default: 0).",
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
    ToolDefinition(
        name="get_project_structure",
        description="Generate a tree-style project structure summary.",
        description_template="Project structure will be displayed",
        tags=("core",),
        func_ref="ayder_cli.tools.builtins.utils_tools:get_project_structure",
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
)