"""
Tool definitions for shell command operations.

Tools: run_shell_command
"""

from typing import Tuple

from ..definition import ToolDefinition

TOOL_DEFINITIONS: Tuple[ToolDefinition, ...] = (
    ToolDefinition(
        name="run_shell_command",
        description="Execute a shell command.",
        description_template="Command `{command}` will be executed",
        tags=("core",),
        func_ref="ayder_cli.tools.builtins.shell:run_shell_command",
        parameters={
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Command to execute.",
                },
            },
            "required": ["command"],
        },
        permission="x",
        safe_mode_blocked=True,
    ),
)