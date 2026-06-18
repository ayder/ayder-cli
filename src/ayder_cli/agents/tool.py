"""Agent tools — discover and delegate to specialized agents.

Provides dynamic ToolDefinitions for registration and factories for sync handlers.
Handlers are sync because they run inside asyncio.to_thread() in the tool
execution pipeline. call_agent schedules work via AgentRegistry.create_run(),
routed onto the event loop through registry._on_loop().
"""

from __future__ import annotations

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
        "Delegate a task to a specialized agent. The agent runs in the background "
        "with its own context and tools. You will receive its summary when it completes. "
        "Use list_agents to discover exact available agent names before calling this tool."
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
        return json.dumps({"agents": registry.list_agents()}, indent=2)

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
