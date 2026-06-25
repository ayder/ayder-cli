"""
Tool definitions for background process operations.

Tools: background_process (consolidated), plus legacy run_background_process /
get_background_output / kill_background_process / list_background_processes
(removed in spec 06 Task 4).

``background_process`` sets ``max_result_chars=0`` to opt out of the chat-loop's
generic 8192-char truncation; its handler self-bounds ``logs`` via offset/max_chars.
"""

from typing import Tuple

from ..definition import ToolDefinition

TOOL_DEFINITIONS: Tuple[ToolDefinition, ...] = (
    ToolDefinition(
        name="background_process",
        description=(
            "Manage background processes (servers, watchers, builds). Single tool "
            "dispatched on `action`: start | logs | stop | list | info. `stop` "
            "group-kills the whole process tree (forked children too). `logs` is "
            "bounded plain text (use tail/max_chars/offset). `info` reports a "
            "process's child pids and listening ports (best-effort)."
        ),
        description_template="Background process action `{action}`",
        tags=("background",),
        func_ref="ayder_cli.tools.builtins.background_process_tool:background_process",
        permission="x",
        safe_mode_blocked=True,
        max_result_chars=0,
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["start", "logs", "stop", "list", "info"],
                    "description": (
                        "Operation. start: launch a command. logs: bounded recent "
                        "output. stop: group-kill the process tree. list: all "
                        "processes (id, os pid, status, command). info: deep "
                        "per-process detail (child pids, listening ports)."
                    ),
                },
                "command": {
                    "type": "string",
                    "description": "[start] Shell command to run in the background.",
                },
                "process_id": {
                    "type": "integer",
                    "description": "[logs/stop/info] The manager id of the process (from list).",
                },
                "tail": {
                    "type": "integer",
                    "description": "[logs] Recent lines to return (default 10). Larger values are char-capped.",
                },
                "max_chars": {
                    "type": "integer",
                    "description": "[logs] Max characters to return (default 4000, capped 8000).",
                },
                "offset": {
                    "type": "integer",
                    "description": "[logs] Char offset to resume from when output was truncated. Default 0.",
                },
            },
            "required": ["action"],
        },
    ),
    ToolDefinition(
        name="run_background_process",
        description="Start a long-running command in the background (servers, watchers, builds).",
        description_template="Background command `{command}` will be started",
        tags=("background",),
        func_ref="ayder_cli.process_manager:run_background_process",
        permission="x",
        safe_mode_blocked=True,
        parameters={
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Command to run in background.",
                },
            },
            "required": ["command"],
        },
    ),
    ToolDefinition(
        name="get_background_output",
        description="Get recent stdout/stderr output from a background process.",
        description_template="Output for background process {process_id} will be retrieved",
        tags=("background",),
        func_ref="ayder_cli.process_manager:get_background_output",
        permission="r",
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
    ),
    ToolDefinition(
        name="kill_background_process",
        description="Kill a running background process.",
        description_template="Background process {process_id} will be killed",
        tags=("background",),
        func_ref="ayder_cli.process_manager:kill_background_process",
        permission="x",
        safe_mode_blocked=True,
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
