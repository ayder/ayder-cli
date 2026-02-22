"""
Tool definitions for background process operations.

Tools: run_background_process, get_background_output, kill_background_process, list_background_processes
"""

from typing import Tuple

from ..definition import ToolDefinition

TOOL_DEFINITIONS: Tuple[ToolDefinition, ...] = (
    ToolDefinition(
        name="run_background_process",
        description="Start a long-running command in the background (servers, watchers, builds).",
        description_template="Background command `{command}` will be started",
        tags=("background",),
        func_ref="ayder_cli.process_manager:run_background_process",
        parameters={
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The command to run in the background (e.g., 'npm run dev', 'python -m http.server')",
                },
            },
            "required": ["command"],
        },
        permission="x",
        safe_mode_blocked=True,
    ),
    ToolDefinition(
        name="get_background_output",
        description="Get recent stdout/stderr output from a background process.",
        description_template="Output for background process {process_id} will be retrieved",
        tags=("background",),
        func_ref="ayder_cli.process_manager:get_background_output",
        parameters={
            "type": "object",
            "properties": {
                "process_id": {
                    "type": "integer",
                    "description": "The ID of the background process",
                },
                "tail": {
                    "type": "integer",
                    "description": "Number of recent lines to return (default: 50)",
                },
            },
            "required": ["process_id"],
        },
        permission="r",
    ),
    ToolDefinition(
        name="kill_background_process",
        description="Kill a running background process.",
        description_template="Background process {process_id} will be killed",
        tags=("background",),
        func_ref="ayder_cli.process_manager:kill_background_process",
        parameters={
            "type": "object",
            "properties": {
                "process_id": {
                    "type": "integer",
                    "description": "The ID of the background process to kill",
                },
            },
            "required": ["process_id"],
        },
        permission="x",
        safe_mode_blocked=True,
    ),
    ToolDefinition(
        name="list_background_processes",
        description="List all background processes and their status.",
        description_template="Background processes will be listed",
        tags=("background",),
        func_ref="ayder_cli.process_manager:list_background_processes",
        parameters={
            "type": "object",
            "properties": {},
        },
        permission="r",
    ),
)