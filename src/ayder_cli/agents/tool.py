"""call_agent tool — delegates tasks to specialized agents.

Provides the ToolDefinition for registration and a factory for the
sync handler. The handler is sync because it runs inside asyncio.to_thread()
in the tool execution pipeline. It calls registry.dispatch() which
schedules the agent via run_coroutine_threadsafe and returns immediately.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable

from ayder_cli.tools.definition import ToolDefinition

if TYPE_CHECKING:
    from ayder_cli.agents.registry import AgentRegistry

logger = logging.getLogger(__name__)

AGENT_TOOL_DEFINITION = ToolDefinition(
    name="call_agent",
    description=(
        "Delegate a task to a specialized agent. The agent runs in the background "
        "with its own context and tools. You will receive its summary when it completes."
    ),
    parameters={
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Agent name from config (e.g., 'code-reviewer', 'test-writer')",
            },
            "task": {
                "type": "string",
                "description": "Task description for the agent to execute",
            },
        },
        "required": ["name", "task"],
    },
    permission="r",
    tags=("core", "agents"),
    system_prompt="",
)


def create_call_agent_handler(registry: AgentRegistry) -> Callable[..., str]:
    """Create a sync handler for the call_agent tool.

    The handler calls registry.dispatch() which is sync and thread-safe.
    It schedules the agent run in the background and returns immediately.
    """

    def handle_call_agent(*, name: str, task: str) -> str:
        return registry.dispatch(name, task)

    return handle_call_agent
