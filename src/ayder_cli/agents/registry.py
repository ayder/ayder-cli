"""AgentRegistry — lifecycle management for agents.

All dispatches are non-blocking (Approach A). dispatch() is a sync method
that schedules agent runs on the event loop via run_coroutine_threadsafe.
Summaries are delivered via _summary_queue, drained by pre_iteration_hook.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

from ayder_cli.agents.config import AgentConfig
from ayder_cli.agents.runner import AgentRunner
from ayder_cli.agents.summary import AgentSummary

logger = logging.getLogger(__name__)


class AgentRegistry:
    """Manages agent lifecycle: dispatch, cancel, status, capability prompts.

    dispatch() is sync and thread-safe — works from both the event loop
    thread and from asyncio.to_thread() background threads (tool pipeline).
    """

    def __init__(
        self,
        agents: dict[str, AgentConfig],
        parent_config: Any,
        project_ctx: Any,
        process_manager: Any,
        permissions: set[str],
        agent_timeout: int = 300,
        on_progress: Callable[[str, str, Any], None] | None = None,
        on_complete: Callable[[AgentSummary], None] | None = None,
    ) -> None:
        self.agents = agents
        self._parent_config = parent_config
        self._project_ctx = project_ctx
        self._process_manager = process_manager
        self._permissions = permissions
        self._agent_timeout = agent_timeout
        self._on_progress = on_progress
        self._on_complete = on_complete
        self._loop: asyncio.AbstractEventLoop | None = None
        self._active: dict[str, AgentRunner] = {}
        self._summary_queue: asyncio.Queue[AgentSummary] = asyncio.Queue()
        self._settled: dict[str, str] = {}

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Set the event loop for scheduling agent runs.

        Must be called after the event loop is running (e.g., in on_mount).
        """
        self._loop = loop

    @property
    def active_count(self) -> int:
        """Number of currently running agents."""
        return len(self._active)

    def get_status(self, name: str) -> str | None:
        """Get agent status: 'idle', 'running', 'completed', 'error', or None if unknown."""
        if name not in self.agents:
            return None
        runner = self._active.get(name)
        if runner is None:
            return "idle"
        return runner.status

    def get_capability_prompts(self) -> str:
        """Generate capability prompt text for the main LLM's system prompt."""
        if not self.agents:
            return ""

        lines = [
            "\n## Available Agents",
            "You can delegate tasks to specialized agents using the call_agent tool.",
            "Each agent runs independently with its own context and may use a different LLM.",
            "",
        ]
        for name, cfg in self.agents.items():
            desc = cfg.system_prompt[:100] if cfg.system_prompt else "(no description)"
            lines.append(f"- {name}: {desc}")

        return "\n".join(lines)

    def dispatch(self, name: str, task: str) -> str:
        """Fire-and-forget agent dispatch. Thread-safe. Returns status message.

        Schedules the agent run on the event loop via run_coroutine_threadsafe.
        Both call_agent tool handler and /agent command use this same method.
        """
        if name not in self.agents:
            return f"Error: Agent '{name}' not found in configured agents"
        if name in self._active:
            return f"Error: Agent '{name}' is already running"
        # Re-dispatch guard: block agents that failed in this cycle
        if name in self._settled and self._settled[name] in ("error", "timeout"):
            return (
                f"Error: Agent '{name}' failed in this cycle "
                f"(status: {self._settled[name]}). Handle the task directly."
            )

        runner = AgentRunner(
            agent_config=self.agents[name],
            parent_config=self._parent_config,
            project_ctx=self._project_ctx,
            process_manager=self._process_manager,
            permissions=self._permissions,
            timeout=self._agent_timeout,
            on_progress=self._on_progress,
        )
        self._active[name] = runner

        async def _run_and_queue():
            result: AgentSummary | None = None
            try:
                result = await runner.run(task)
                await self._summary_queue.put(result)
            finally:
                # These two operations must stay together without an await between
                # them to ensure active_count is accurate when on_complete fires
                self._active.pop(name, None)
                if result is not None:
                    self._settled[name] = result.status
                if self._on_complete is not None and result is not None:
                    try:
                        self._on_complete(result)
                    except Exception:
                        logger.exception("on_complete callback failed")

        # Schedule on event loop (thread-safe)
        if self._loop is None:
            self._active.pop(name, None)
            return "Error: Agent registry not initialized (event loop not set)"
        asyncio.run_coroutine_threadsafe(_run_and_queue(), self._loop)

        task_preview = task[:80] + "..." if len(task) > 80 else task
        return (
            f"Agent '{name}' dispatched with task: {task_preview}\n"
            f"The agent is running in the background. "
            f"You will receive its summary when it completes."
        )

    def cancel(self, name: str) -> bool:
        """Cancel a running agent. Returns True if cancelled, False if not running."""
        runner = self._active.get(name)
        if runner is None:
            return False
        return runner.cancel()

    def reset_settled(self) -> None:
        """Clear the settled tracker. Call on new user message cycle."""
        self._settled = {}

    def drain_summaries(self) -> list[AgentSummary]:
        """Drain all completed summaries from the queue (non-blocking)."""
        summaries = []
        while not self._summary_queue.empty():
            try:
                summaries.append(self._summary_queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return summaries
