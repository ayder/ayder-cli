"""
Tool definitions for shell command operations.

Tools: bash
"""

from typing import Tuple

from ..definition import ToolDefinition

TOOL_DEFINITIONS: Tuple[ToolDefinition, ...] = (
    ToolDefinition(
        name="bash",
        description=(
            "Run a shell command and return its exit code, stdout, and stderr. "
            "Use for builds, tests, git, file inspection, and other terminal tasks."
        ),
        description_template="Command `{command}` will be executed",
        tags=("core",),
        func_ref="ayder_cli.tools.builtins.shell:bash",
        parameters={
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Command to execute.",
                },
                "shell": {
                    "type": "string",
                    "enum": ["bash", "zsh", "sh", "busybox"],
                    "description": "Shell to run the command under (default bash).",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Max seconds to run (default 120, clamped to 1-600).",
                },
                "environment": {
                    "type": "object",
                    "description": "Env vars overlaid on the inherited environment.",
                    "additionalProperties": {"type": "string"},
                },
            },
            "required": ["command"],
        },
        permission="x",
        safe_mode_blocked=True,
    ),
)
