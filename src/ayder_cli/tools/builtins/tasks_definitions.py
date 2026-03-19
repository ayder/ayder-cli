"""
Tool definitions for task management operations.

Tools: list_tasks, show_task
"""

from typing import Tuple

from ..definition import ToolDefinition

TOOL_DEFINITIONS: Tuple[ToolDefinition, ...] = (
    ToolDefinition(
        name="list_tasks",
        description="List task files in .ayder/tasks/ directory, filtered by status (default: pending tasks only).",
        description_template="Task files will be listed",
        tags=("metadata",),
        func_ref="ayder_cli.tools.builtins.tasks:list_tasks",
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
        tags=("metadata",),
        func_ref="ayder_cli.tools.builtins.tasks:show_task",
        parameters={
            "type": "object",
            "properties": {
                "identifier": {
                    "type": "string",
                    "description": "Task identifier (ID, path, or slug).",
                },
            },
            "required": ["identifier"],
        },
        permission="r",
    ),
)