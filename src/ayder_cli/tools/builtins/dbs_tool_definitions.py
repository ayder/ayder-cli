"""
Tool definitions for DBS RAG API operations.

Tools: dbs_tool
"""

from typing import Tuple

from ..definition import ToolDefinition

TOOL_DEFINITIONS: Tuple[ToolDefinition, ...] = (
    ToolDefinition(
        name="dbs_tool",
        description=(
            "Query the DBS RAG API for DBS-related issues/tasks/docs (mode='md') "
            "or SQL queries/files (mode='sql')."
        ),
        description_template="DBS RAG query with mode '{mode}'",
        tags=("dbs",),
        system_prompt="\nA RAG server only related with DBS issues. Use this tool for DBS related requests\n",
        func_ref="ayder_cli.tools.builtins.dbs_tool:dbs_tool",
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Semantic query text to search in DBS RAG index",
                },
                "mode": {
                    "type": "string",
                    "enum": ["md", "sql"],
                    "description": "Search target: md for issues/tasks/docs, sql for SQL queries/files",
                },
                "url": {
                    "type": "string",
                    "description": "Base API URL (default: http://127.0.0.1:8000)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results to return",
                },
                "source_filter": {
                    "type": "string",
                    "description": "Optional exact-match source filter",
                },
                "min_time": {
                    "type": "number",
                    "description": "SQL mode only: minimum execution time (ms)",
                },
                "timeout_seconds": {
                    "type": "integer",
                    "description": "Request timeout in seconds (default: 60)",
                },
            },
            "required": ["query", "mode"],
        },
        permission="http",
        safe_mode_blocked=True,
    ),
)
