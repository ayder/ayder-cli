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
        on_progress: Callable[[int, str, str, Any], None] | None = None,
        on_complete: Callable[[int, AgentSummary], None] | None = None,
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
        self._active: dict[int, AgentRunner] = {}  # run_id -> runner
        self._run_counter: int = 0
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
        """Get agent status: aggregate across all instances."""
        if name not in self.agents:
            return None
        # Check for any running instance
        for runner in self._active.values():
            if runner.agent_name == name:
                return "running"
        # Check settled status
        if name in self._settled:
            return self._settled[name]
        return "idle"

    def get_running_count(self, name: str) -> int:
        """Count of currently active instances of the named agent."""
        return sum(1 for r in self._active.values() if r.agent_name == name)

    def get_capability_prompts(self) -> str:
        """Generate capability prompt text for the main LLM's system prompt."""
        if not self.agents:
            return ""

        lines = [
            "\n## Available Agents",
            "You can delegate tasks to specialized agents using the call_agent tool.",
            "Each agent runs independently with its own context and may use a different LLM.",
            "",
            "**Batch behavior:** When you dispatch multiple agents, you will receive",
            "all their summaries together after the last agent completes.",
            "Do not respond until you have all results.",
            "",
            "**On agent failure:** If an agent fails (error/timeout), do NOT re-dispatch it.",
            "Handle the failed task yourself. Agents that completed successfully CAN be",
            "re-dispatched if needed (e.g., to re-run tests after fixing code).",
            "",
        ]
        for name, cfg in self.agents.items():
            desc = cfg.system_prompt[:100] if cfg.system_prompt else "(no description)"
            lines.append(f"- {name}: {desc}")

        return "\n".join(lines)

    def dispatch(self, name: str, task: str) -> int | str:
        """Fire-and-forget agent dispatch. Thread-safe.

        Returns run_id (int) on success, error message (str) on failure.
        """
        if name not in self.agents:
            logger.debug("dispatch rejected: agent '%s' not found", name)
            return f"Error: Agent '{name}' not found in configured agents"
        # Re-dispatch guard: block agents that failed in this cycle
        if name in self._settled and self._settled[name] in ("error", "timeout"):
            logger.debug(
                "dispatch blocked by _settled guard: agent='%s' status='%s'",
                name, self._settled[name],
            )
            return (
                f"Error: Agent '{name}' failed in this cycle "
                f"(status: {self._settled[name]}). Handle the task directly."
            )

        self._run_counter += 1
        run_id = self._run_counter

        runner = AgentRunner(
            agent_config=self.agents[name],
            parent_config=self._parent_config,
            project_ctx=self._project_ctx,
            process_manager=self._process_manager,
            permissions=self._permissions,
            timeout=self._agent_timeout,
            run_id=run_id,
            on_progress=self._on_progress,
        )
        self._active[run_id] = runner
        task_preview = task[:120] + "..." if len(task) > 120 else task
        logger.debug(
            "dispatch: agent='%s' run_id=%d task='%s' active_count=%d",
            name, run_id, task_preview, self.active_count,
        )

        async def _run_and_queue():
            result: AgentSummary | None = None
            try:
                result = await runner.run(task)
                await self._summary_queue.put(result)
            finally:
                self._active.pop(run_id, None)
                if result is not None:
                    self._settled[name] = result.status
                    logger.debug(
                        "agent finished: agent='%s' run_id=%d status='%s' "
                        "active_count=%d settled='%s'",
                        name, run_id, result.status,
                        self.active_count, result.status,
                    )
                else:
                    logger.debug(
                        "agent finished with no result: agent='%s' run_id=%d "
                        "active_count=%d",
                        name, run_id, self.active_count,
                    )
                if self._on_complete is not None and result is not None:
                    try:
                        self._on_complete(run_id, result)
                    except Exception:
                        logger.exception("on_complete callback failed")

        # Schedule on event loop (thread-safe)
        if self._loop is None:
            self._active.pop(run_id, None)
            return "Error: Agent registry not initialized (event loop not set)"
        asyncio.run_coroutine_threadsafe(_run_and_queue(), self._loop)

        return run_id

    def cancel(self, name: str) -> bool:
        """Cancel all running instances of the named agent. Returns True if any cancelled."""
        to_cancel = [rid for rid, r in self._active.items() if r.agent_name == name]
        for rid in to_cancel:
            self._active[rid].cancel()
        if to_cancel:
            logger.debug("cancel: agent='%s' cancelled %d instance(s): %s", name, len(to_cancel), to_cancel)
        else:
            logger.debug("cancel: agent='%s' — no running instances", name)
        return len(to_cancel) > 0

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
        if summaries:
            agents = [(s.agent_name, s.status) for s in summaries]
            logger.debug("drain_summaries: %d summaries drained: %s", len(summaries), agents)
        return summaries

    def has_pending_summaries(self) -> bool:
        """Return True if any completed agent summaries are waiting to be drained.

        Non-destructive — does not remove items from the queue.
        Safe to call from the event loop thread.
        """
        return not self._summary_queue.empty()
