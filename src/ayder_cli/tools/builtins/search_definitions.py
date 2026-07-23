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
        description=(
            "Search file contents with a regex. Scope with 'directory' "
            "(a directory or a single file) and/or a 'file_pattern' glob."
        ),
        description_template="Codebase will be searched for pattern '{pattern}'",
        parameters={
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Regex pattern to search for. Patterns starting with '-' (e.g. '-> str') are safe.",
                },
                "file_pattern": {
                    "type": "string",
                    "description": (
                        "Optional glob filter. 'core.py' matches that filename in "
                        "any directory; 'src/core.py' anchors to that exact path; "
                        "'*.py' filters by extension; 'src/**/*.py' scopes a subtree."
                    ),
                },
                "case_sensitive": {
                    "type": "boolean",
                    "description": "Whether the search is case-sensitive (default: true)",
                },
                "context_lines": {
                    "type": "integer",
                    "description": "Context lines around each match, shown only with output_format 'full' (default: 0).",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum matches shown for 'full'/'locations' output (default: 50). The output says so when results are truncated.",
                },
                "directory": {
                    "type": "string",
                    "description": "Directory or single file to search (default: '.'). E.g. 'src' or 'src/core.py'.",
                },
                "output_format": {
                    "type": "string",
                    "enum": ["full", "files_only", "count", "locations"],
                    "description": (
                        "Output format: 'full' (default, matching lines), "
                        "'files_only' (file paths only), 'count' (match counts "
                        "per file), 'locations' (file and line numbers, no content "
                        "— cheapest way to see exactly where matches are)"
                    ),
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