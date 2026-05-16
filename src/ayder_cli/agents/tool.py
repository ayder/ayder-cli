"""Agent tools — discover and delegate to specialized agents.

Provides dynamic ToolDefinitions for registration and factories for sync handlers.
Handlers are sync because they run inside asyncio.to_thread() in the tool
execution pipeline. call_agent schedules work via AgentRegistry.dispatch().
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

    The handler calls registry.dispatch() which is sync and thread-safe.
    It schedules the agent run in the background and returns immediately.
    """

    def handle_call_agent(*, name: str, task: str) -> str:
        result = registry.dispatch(name, task)
        if isinstance(result, int):
            task_preview = task[:80] + "..." if len(task) > 80 else task
            return (
                f"Agent '{name}' dispatched successfully with task: {task_preview}\n"
                f"The agent is running in the background. "
                f"You will receive its summary when it completes."
            )
        return result  # error string

    return handle_call_agent
