"""
Tool definitions for task management operations.

Tools: list_tasks, show_task
"""

from typing import Tuple

from .definition import ToolDefinition

TOOL_DEFINITIONS: Tuple[ToolDefinition, ...] = (
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