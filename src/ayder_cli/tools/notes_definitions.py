"""
Tool definitions for notes operations.

Tools: create_note
"""

from typing import Tuple

from .definition import ToolDefinition

TOOL_DEFINITIONS: Tuple[ToolDefinition, ...] = (
    ToolDefinition(
        name="create_note",
        description="Create a markdown note in .ayder/notes/ for investigation findings or documentation.",
        description_template="Note '{title}' will be created",
        tags=("metadata",),
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
)