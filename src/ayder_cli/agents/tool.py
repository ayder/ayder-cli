"""Agent tools — discover and delegate to specialized agents.

Provides dynamic ToolDefinitions for registration and factories for sync handlers.
Handlers are sync because they run inside asyncio.to_thread() in the tool
execution pipeline. call_agent schedules work via AgentRegistry.create_run(),
routed onto the event loop through registry._on_loop().
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

LIST_AGENTS_TOOL_DEFINITION = ToolDefinition(
    name="list_agents",
    description=(
        "List configured specialized agents with exact names, descriptions, "
        "status, and running counts. Use this before call_agent when you need "
        "to discover available agent names."
    ),
    parameters={
        "type": "object",
        "properties": {},
        "required": [],
    },
    permission="r",
    tags=("core", "agents"),
    system_prompt="",
)

AGENT_TOOL_DEFINITION = ToolDefinition(
    name="call_agent",
    description=(
        "Delegate a task to a specialized agent that runs in the background. "
        "Returns a run id immediately; poll agent_status and collect with read_agent_result. "
        "Use list_agents to discover names first."
    ),
    parameters={
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Exact agent name returned by list_agents",
            },
            "task": {
                "type": "string",
                "description": "Clear task description for the agent to execute",
            },
        },
        "required": ["name", "task"],
    },
    permission="r",
    tags=("core", "agents"),
    system_prompt="",
)


def create_list_agents_handler(registry: AgentRegistry) -> Callable[..., str]:
    """Create a sync handler for the list_agents tool."""

    def handle_list_agents() -> str:
        return json.dumps({"agents": registry._on_loop(lambda: registry.list_agents())}, indent=2)

    return handle_list_agents


def create_call_agent_handler(registry: AgentRegistry) -> Callable[..., str]:
    """Create a sync handler for the call_agent tool.

    The handler routes registry.create_run() onto the event loop via
    registry._on_loop() (the handler runs in a worker thread). The agent runs
    in the background; the main LLM collects results via the pull tools.
    """

    def handle_call_agent(*, name: str, task: str) -> str:
        result = registry._on_loop(lambda: registry.create_run(name, task))
        if isinstance(result, int):
            return (
                f"Dispatched '{name}' as run #{result} (working). "
                f"Poll with agent_status; collect with read_agent_result({result})."
            )
        return result  # error string

    return handle_call_agent


AGENT_STATUS_TOOL_DEFINITION = ToolDefinition(
    name="agent_status",
    description=("Show all agent runs you dispatched this conversation with their status "
                 "(working/done/error), elapsed seconds, and whether a result is unread. "
                 "Use read_agent_result(run_id) to collect a finished one."),
    parameters={"type": "object", "properties": {}, "required": []},
    permission="r", tags=("core", "agents"), system_prompt="",
)

READ_AGENT_RESULT_TOOL_DEFINITION = ToolDefinition(
    name="read_agent_result",
    description=("Collect a dispatched agent's deliverable by run id. Marks it read. "
                 "Set wait=true to block until it finishes (up to timeout_s seconds)."),
    parameters={"type": "object", "properties": {
        "run_id": {"type": "integer", "description": "The run id from call_agent / agent_status"},
        "wait": {"type": "boolean", "description": "Block until the agent finishes (default false)"},
        "timeout_s": {"type": "integer", "description": "Max seconds to block when wait=true (default 60)"},
    }, "required": ["run_id"]},
    permission="r", tags=("core", "agents"), system_prompt="",
)


def create_agent_status_handler(registry: AgentRegistry) -> Callable[..., str]:
    """Create a sync handler for the agent_status tool."""

    def handle_agent_status() -> str:
        return json.dumps({"agents": registry._on_loop(lambda: registry.snapshot())}, indent=2)

    return handle_agent_status


def create_read_agent_result_handler(registry: AgentRegistry) -> Callable[..., str]:
    """Create a sync handler for the read_agent_result tool.

    When wait=True, blocks the calling thread using run_coroutine_threadsafe
    so the event loop can keep running (await_run is a coroutine).
    """

    def handle_read_agent_result(*, run_id: int, wait: bool = False, timeout_s: int = 60) -> str:
        if wait:
            payload = asyncio.run_coroutine_threadsafe(
                registry.await_run(run_id, timeout_s), registry._loop
            ).result() if registry._loop is not None else None
        else:
            payload = registry._on_loop(lambda: registry.read_result(run_id))
        if payload is None:
            return json.dumps({"error": f"No agent run #{run_id} in this conversation."})
        return json.dumps(payload, indent=2)

    return handle_read_agent_result
