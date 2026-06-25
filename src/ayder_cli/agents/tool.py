"""Agent tool — discover and delegate to specialized agents.

Provides the dynamic ToolDefinition and sync handler factory for the consolidated
agent(action=...) tool. Handlers are sync because they run inside
asyncio.to_thread() in the tool execution pipeline.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Callable

from ayder_cli.tools.definition import ToolDefinition

if TYPE_CHECKING:
    from ayder_cli.agents.registry import AgentRegistry

logger = logging.getLogger(__name__)

AGENT_TOOL_DEFINITION = ToolDefinition(
    name="agent",
    description=(
        "Discover and delegate to specialized background agents. Single tool, "
        "dispatched on `action`: list (configured agents), call (dispatch one; "
        "returns a run id immediately), status (your runs this turn), read_result "
        "(collect a finished run by run_id; set wait=true to block up to timeout_s). "
        "You PULL results — they are not pushed. When the work is a task file under "
        ".ayder/tasks/, pass its task_id and the harness hands the agent the file itself."
    ),
    description_template="agent `{action}`",
    parameters={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["call", "list", "status", "read_result"],
                "description": (
                    "list: enumerate configured agents. call: dispatch `name` with "
                    "`task` (+ optional task_id/branch_name). status: list your runs. "
                    "read_result: collect `run_id` (optionally wait)."
                ),
            },
            "name": {
                "type": "string",
                "description": "[call] Exact agent name from action=list.",
            },
            "task": {
                "type": "string",
                "description": (
                    "[call] The agent's entire user turn — it has no other context. Optional "
                    "ONLY when task_id is given; otherwise concrete and non-empty: what to do, "
                    "the files/branch, the acceptance criteria."
                ),
            },
            "task_id": {
                "type": "string",
                "description": (
                    "[call] Optional task this implements, e.g. 'TASK-003' (or '3'). Resolved "
                    "against .ayder/tasks/ and FAILS FAST if missing; on resolution the file is "
                    "embedded in the agent's prompt."
                ),
            },
            "branch_name": {
                "type": "string",
                "description": (
                    "[call] Optional git branch the agent must work and COMMIT on, e.g. "
                    "'agent/add-auth'. Folded into the agent's instructions."
                ),
            },
            "run_id": {
                "type": "integer",
                "description": "[read_result] The run id from action=call / action=status.",
            },
            "wait": {
                "type": "boolean",
                "description": "[read_result] Block until the agent finishes (default false).",
            },
            "timeout_s": {
                "type": "integer",
                "description": "[read_result] Max seconds to block when wait=true (default 60).",
            },
        },
        "required": ["action"],
    },
    permission="r",
    tags=("core", "agents"),
    max_result_chars=0,
    system_prompt="",
)


def create_agent_handler(registry: AgentRegistry) -> Callable[..., str]:
    """Sync dispatcher for the consolidated `agent` tool.

    Routes `action` to the existing registry entry points. Runs in a worker
    thread: loop-owned reads go through registry._on_loop(); the read_result
    wait path uses run_coroutine_threadsafe so the loop keeps running.
    """

    def handle_agent(
        *,
        action: str,
        name: str | None = None,
        task: str = "",
        task_id: str | None = None,
        branch_name: str | None = None,
        run_id: int | None = None,
        wait: bool = False,
        timeout_s: int = 60,
    ) -> str:
        act = (action or "").strip().lower()

        if act == "list":
            return json.dumps(
                {"agents": registry._on_loop(lambda: registry.list_agents())}, indent=2
            )

        if act == "status":
            return json.dumps(
                {"agents": registry._on_loop(lambda: registry.snapshot())}, indent=2
            )

        if act == "call":
            if not name:
                return (
                    "Error: action=call requires `name` "
                    '(use agent(action="list") to discover names).'
                )
            result = registry._on_loop(
                lambda: registry.create_run(name, task, task_id=task_id, branch_name=branch_name)
            )
            if isinstance(result, int):
                label = registry._on_loop(lambda: registry.run_label(result))
                bound = f" for {label}" if label else ""
                return (
                    f"Dispatched '{name}' as run #{result}{bound}. "
                    f'Poll with agent(action="status"); collect with '
                    f'agent(action="read_result", run_id={result}).'
                )
            return result

        if act == "read_result":
            if run_id is None:
                return json.dumps({"error": "action=read_result requires run_id."})
            if wait:
                payload = (
                    asyncio.run_coroutine_threadsafe(
                        registry.await_run(run_id, timeout_s), registry._loop
                    ).result()
                    if registry._loop is not None
                    else None
                )
            else:
                payload = registry._on_loop(lambda: registry.read_result(run_id))
            if payload is None:
                return json.dumps({"error": f"No agent run #{run_id} in this conversation."})
            return json.dumps(payload, indent=2)

        return json.dumps(
            {"error": f"Unknown action '{action}'. Valid: call, list, status, read_result."}
        )

    return handle_agent
