"""Tool definition for the consolidated ``task(action=...)`` tool.

Auto-discovered by ``tools/definition.py:_discover_definitions`` — dropping this
file in ``tools/builtins/`` is sufficient to register the tool; no core edit.

``max_result_chars=0`` exempts the tool from the chat-loop's generic 8192-char
truncation (which would otherwise *replace* over-budget output with a useless
structural summary). The handler self-bounds every action's output via
``limit`` / ``offset`` / ``section`` / ``max_chars`` instead.
"""

from typing import Tuple

from ..definition import ToolDefinition

TOOL_DEFINITIONS: Tuple[ToolDefinition, ...] = (
    ToolDefinition(
        name="task",
        description=(
            "Manage .ayder/tasks/ task files. Single tool, dispatched on "
            "`action`: create | list | show | status | update_status | update. "
            "Output is bounded plain text (use offset/limit/max_chars/section to "
            "page); prefer this over file_editor for all task operations."
        ),
        description_template="Task action `{action}`",
        tags=("metadata",),
        func_ref="ayder_cli.tools.builtins.task_tool:task",
        permission="w",
        max_result_chars=0,
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "create",
                        "list",
                        "show",
                        "status",
                        "update_status",
                        "update",
                    ],
                    "description": (
                        "Operation to perform. create: new task. list: paged "
                        "rows. show: bounded body/section. status: current "
                        "status. update_status: change status. update: replace "
                        "one PRD section."
                    ),
                },
                "title": {
                    "type": "string",
                    "description": "[create] Task title (required for create).",
                },
                "body": {
                    "type": "string",
                    "description": (
                        "[create] PRD markdown body (## Goal / ## Files / "
                        "## Acceptance Criteria / ## Notes). Any H1 or "
                        "## Signature block you include is stripped — the tool "
                        "owns the title and signature."
                    ),
                },
                "dependencies": {
                    "type": "string",
                    "description": (
                        "[create] Comma-separated task IDs this depends on, e.g. "
                        "'TASK-003,TASK-004' or '3,4'."
                    ),
                },
                "branch": {
                    "type": "string",
                    "description": (
                        "[create] Working branch. Defaults to 'agent/<slug>'."
                    ),
                },
                "status": {
                    "type": "string",
                    "enum": ["pending", "in_progress", "done", "blocked"],
                    "description": (
                        "[create] initial status (default pending); "
                        "[update_status] target status (required). "
                        "[list] status filter (also accepts 'all')."
                    ),
                },
                "identifier": {
                    "type": "string",
                    "description": (
                        "[show/status/update_status/update] Task identifier: ID "
                        "('7', '007', 'TASK-007'), filename, path, or slug."
                    ),
                },
                "section": {
                    "type": "string",
                    "description": (
                        "[show] return only this PRD section; [update] the "
                        "section to replace (required; 'Signature' is rejected)."
                    ),
                },
                "content": {
                    "type": "string",
                    "description": "[update] New body for the named section (required).",
                },
                "meta_only": {
                    "type": "boolean",
                    "description": "[show] Return only the Signature block.",
                },
                "max_chars": {
                    "type": "integer",
                    "description": (
                        "[show] Max characters to return (default 4000, capped "
                        "at 8000). Truncated output ends with a continuation hint."
                    ),
                },
                "offset": {
                    "type": "integer",
                    "description": (
                        "[show] byte offset to resume from; [list] row offset for "
                        "paging. Default 0."
                    ),
                },
                "limit": {
                    "type": "integer",
                    "description": (
                        "[list] Max rows to return (default 30, capped at 100)."
                    ),
                },
            },
            "required": ["action"],
        },
    ),
)
