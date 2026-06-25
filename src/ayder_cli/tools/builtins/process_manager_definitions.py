"""
Tool definitions for background process operations.

Tools: background_process (consolidated).

``background_process`` sets ``max_result_chars=0`` to opt out of the chat-loop's
generic tool-result truncation; its handler self-bounds ``logs`` via offset/max_chars.
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
)
