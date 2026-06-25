"""
Tool definitions for notes operations.

Tools: note (consolidated), create_note (legacy — removed in spec 04 Task 3).

``note`` sets ``max_result_chars=0`` to opt out of the chat-loop's generic
8192-char truncation; its handler self-bounds via offset/max_chars/limit.
"""

from typing import Tuple

from ..definition import ToolDefinition

TOOL_DEFINITIONS: Tuple[ToolDefinition, ...] = (
    ToolDefinition(
        name="note",
        description=(
            "Manage .ayder/notes/ note files. Single tool dispatched on `action`: "
            "create | read | update | list | delete. Notes are caller-named (you "
            "choose `note_id`); create fails if the id already exists (then use "
            "read/update). Output is bounded plain text (use offset/max_chars/limit "
            "to page); prefer this over file_editor for note operations."
        ),
        description_template="Note action `{action}`",
        tags=("metadata",),
        func_ref="ayder_cli.tools.builtins.note_tool:note",
        permission="w",
        safe_mode_blocked=False,
        max_result_chars=0,
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["create", "read", "update", "list", "delete"],
                    "description": (
                        "Operation. create: new note (fails if id exists). read: "
                        "bounded body. update: append (default) or replace body. "
                        "list: paged ids. delete: remove a note."
                    ),
                },
                "note_id": {
                    "type": "string",
                    "description": (
                        "[create/read/update/delete] Caller-chosen id/name, e.g. "
                        "'plan-add-auth' or 'agent-wander-task-003'. Normalized to a "
                        "slug, so 'Agent Wander TASK-003' maps to the same note."
                    ),
                },
                "content": {
                    "type": "string",
                    "description": "[create/update] Markdown body (required for create/update).",
                },
                "tags": {
                    "type": "string",
                    "description": "[create] Comma-separated tags, e.g. 'bug,security'.",
                },
                "mode": {
                    "type": "string",
                    "enum": ["append", "replace"],
                    "description": (
                        "[update] append (default) adds a dated entry and keeps prior "
                        "content; replace overwrites the body."
                    ),
                },
                "max_chars": {
                    "type": "integer",
                    "description": (
                        "[read] Max characters to return (default 4000, capped at "
                        "8000). Truncated output ends with a continuation hint."
                    ),
                },
                "offset": {
                    "type": "integer",
                    "description": (
                        "[read] byte offset to resume from; [list] row offset for "
                        "paging. Default 0."
                    ),
                },
                "limit": {
                    "type": "integer",
                    "description": "[list] Max rows to return (default 30, capped at 100).",
                },
                "prefix": {
                    "type": "string",
                    "description": "[list] Filter ids by this normalized prefix (e.g. 'agent-wander').",
                },
            },
            "required": ["action"],
        },
    ),
    ToolDefinition(
        name="create_note",
        description="Create a markdown note in .ayder/notes/ for investigation findings or documentation.",
        description_template="Note '{title}' will be created",
        tags=("metadata",),
        func_ref="ayder_cli.tools.builtins.notes:create_note",
        parameters={
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "The title of the note"},
                "content": {"type": "string", "description": "The markdown content of the note"},
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
