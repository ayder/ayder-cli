"""Tool definition for the unified context tool."""

from typing import Tuple

from ..definition import ToolDefinition


TOOL_DEFINITIONS: Tuple[ToolDefinition, ...] = (
    ToolDefinition(
        name="context",
        description=(
            "Session context. action=save snapshots state by name; "
            "load restores by name; list enumerates slots; "
            "stats reports token + cache usage; "
            "clear auto-saves the caller-provided summary and deferred-wipes."
        ),
        description_template="Context action `{action}` will run",
        tags=("core",),
        func_ref="ayder_cli.tools.builtins.context:context",
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["save", "load", "list", "stats", "clear"],
                    "description": "Operation to perform.",
                },
                "name": {
                    "type": "string",
                    "description": "Slot name. Required for save and load.",
                },
                "content": {
                    "type": "string",
                    "description": (
                        "Content. Required for save and clear."
                    ),
                },
                "overwrite": {
                    "type": "boolean",
                    "description": "Save: skip auto-versioning of existing slot.",
                },
                "keep_last_n": {
                    "type": "integer",
                    "description": (
                        "Clear: number of most-recent message exchanges to retain."
                    ),
                },
            },
            "required": ["action"],
        },
        permission="w",
        safe_mode_blocked=False,
    ),
)
