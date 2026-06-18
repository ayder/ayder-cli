"""AgentRegistry — lifecycle management for agents.

All registry result state (the AgentRun records) is owned by the event loop.
create_run() schedules agent runs via asyncio.create_task and MUST run on the
loop; worker threads marshal through _on_loop(). The main LLM polls/drains
results via the pull API (snapshot/read_result/await_run); completions nudge
the idle LLM rather than pushing summaries into its context.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable

from ayder_cli.agents.config import AgentConfig
from ayder_cli.agents.run import AgentRun
from ayder_cli.agents.runner import AgentRunner, AgentRunOutcome

logger = logging.getLogger(__name__)


class AgentRegistry:
    """Manages agent lifecycle: create_run, cancel, status, capability prompts.

    Registry result state (the AgentRun records) is loop-owned. create_run()
    runs on the event loop and schedules runs with asyncio.create_task; worker
    threads must route mutations through _on_loop() (single-loop invariant).
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
        on_complete: Callable[[int, AgentRun], None] | None = None,
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
        self._runs: dict[int, AgentRun] = {}
        self._current_generation: int = 0
        self._settled: dict[str, str] = {}

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Set the event loop for scheduling agent runs.

        Must be called after the event loop is running (e.g., in on_mount).
        """
        self._loop = loop

    @property
    def active_count(self) -> int:
        """Number of currently running (working) agents."""
        return sum(1 for r in self._runs.values() if r.status == "working")

    @property
    def current_generation(self) -> int:
        return self._current_generation

    def new_generation(self) -> int:
        """Bump the conversation generation and reset the re-dispatch guard.
        Does NOT drop _runs: active agents keep running and are simply filtered
        out of delivery (snapshot/read/nudge) for the new conversation."""
        self._current_generation += 1
        self._settled = {}
        return self._current_generation

    async def _on_loop_coro(self, fn):
        return fn()

    def _on_loop(self, fn):
        """Run fn() on the owning event loop from a worker thread; return its result.

        Fails explicitly if the loop is unset — registry state is loop-owned, so a
        worker thread must never read/mutate it directly (single-loop invariant, §4).
        """
        if self._loop is None:
            raise RuntimeError("AgentRegistry loop not set (call set_loop first)")
        return asyncio.run_coroutine_threadsafe(self._on_loop_coro(fn), self._loop).result()

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

    def list_agents(self) -> list[dict[str, Any]]:
        """Return configured agents with live status information."""
        parent_model = getattr(self._parent_config, "model", None)
        agents: list[dict[str, Any]] = []
        for name, cfg in self.agents.items():
            description = cfg.system_prompt[:200] if cfg.system_prompt else ""
            resolved_model = cfg.model or parent_model
            model = resolved_model if isinstance(resolved_model, str) else ""
            agents.append({
                "name": name,
                "description": description,
                "model": model,
                "status": self.get_status(name) or "unknown",
                "running_count": self.get_running_count(name),
            })
        return agents

    def get_capability_prompts(self) -> str:
        """Generate generic agent capability guidance for the system prompt."""
        if not self.agents:
            return ""

        lines = [
            "\n## Agent Delegation",
            "",
            "Configured specialized agents may be available. Use `list_agents` to discover "
            "exact names before `call_agent`. Each runs in the background with its own LLM.",
            "",
            "**You pull results — they are not delivered automatically.** `call_agent` returns "
            "a run id. Use `agent_status()` to see what is working/done, and "
            "`read_agent_result(run_id)` to collect a finished one. To wait for an agent, call "
            "`read_agent_result(run_id, wait=true, timeout_s=…)` instead of polling in a loop.",
            "",
            "Each finished run has a best-effort `note_path` to its full saved deliverable; if a "
            "result has scrolled out of context, `read_file` that path instead of re-dispatching.",
            "If you end your turn with results unread, you will be nudged once to collect them.",
            "",
            "**Rules:** dispatch the same agent multiple times if useful; only use an agent whose "
            "specialty matches; on failure, handle the task yourself — do not re-dispatch a failed agent.",
        ]

        return "\n".join(lines)

    def create_run(self, name: str, task: str) -> int | str:
        """Create an AgentRun and schedule it. MUST run on the event loop.
        Returns run_id (int) or an error string."""
        if name not in self.agents:
            available = ", ".join(sorted(self.agents))
            return (f"Error: Agent '{name}' not found. Available: {available}. Call list_agents."
                    if available else
                    "Error: Agent '{name}' not found. No agents configured.".format(name=name))
        if name in self._settled and self._settled[name] in ("error", "timeout"):
            return (f"Error: Agent '{name}' failed in this cycle "
                    f"(status: {self._settled[name]}). Handle the task directly.")
        if self._loop is None:
            return "Error: Agent registry not initialized (event loop not set)"

        self._run_counter += 1
        run_id = self._run_counter
        runner = AgentRunner(
            agent_config=self.agents[name], parent_config=self._parent_config,
            project_ctx=self._project_ctx, process_manager=self._process_manager,
            permissions=self._permissions, timeout=self._agent_timeout,
            run_id=run_id, generation=self._current_generation, on_progress=self._on_progress,
        )
        run = AgentRun(run_id=run_id, generation=self._current_generation,
                       agent_name=name, started_at=time.monotonic())
        self._runs[run_id] = run
        self._active[run_id] = runner
        asyncio.create_task(self._run_and_queue(run, runner, task))
        return run_id

    async def _run_and_queue(self, run: AgentRun, runner: AgentRunner, task: str) -> None:
        outcome: AgentRunOutcome | None = None
        try:
            outcome = await runner.run(task)
        except Exception:
            logger.exception("agent run crashed: run_id=%d", run.run_id)
            outcome = AgentRunOutcome("error", "Agent encountered an error.", "internal error", None)
        finally:
            self._active.pop(run.run_id, None)
            if outcome is not None:
                run.status = outcome.status
                run.result = outcome.content
                run.error = outcome.error
                run.note_path = outcome.note_path
            run.finished_at = time.monotonic()
            run.done_event.set()
            if run.generation == self._current_generation and outcome is not None:
                self._settled[run.agent_name] = outcome.status
            if self._on_complete is not None:
                try:
                    self._on_complete(run.run_id, run)
                except Exception:
                    logger.exception("on_complete callback failed")

    def snapshot(self) -> list[dict]:
        now = time.monotonic()
        runs = [r for r in self._runs.values() if r.generation == self._current_generation]
        runs.sort(key=lambda r: r.run_id, reverse=True)
        return [r.to_status_dict(now=now) for r in runs]

    def _result_payload(self, run: AgentRun) -> dict:
        """Full payload for a TERMINAL run; marks it drained. Never call on a working run."""
        run.drained = True
        return {"run_id": run.run_id, "name": run.agent_name, "status": run.status,
                "result": run.result, "note_path": run.note_path,
                "working_time_s": run.working_time(now=time.monotonic()), "error": run.error}

    def read_result(self, run_id: int) -> dict | None:
        run = self._runs.get(run_id)
        if run is None or run.generation != self._current_generation:
            return None
        if run.status == "working":
            return run.to_status_dict(now=time.monotonic())   # NOT drained (finding 1)
        return self._result_payload(run)                       # terminal -> drains

    async def await_run(self, run_id: int, timeout_s: float) -> dict | None:
        run = self._runs.get(run_id)
        if run is None or run.generation != self._current_generation:
            return None
        if run.status == "working":
            capped = max(0.0, min(float(timeout_s), float(self._agent_timeout)))
            try:
                await asyncio.wait_for(run.done_event.wait(), timeout=capped)
            except asyncio.TimeoutError:
                return run.to_status_dict(now=time.monotonic())  # still working, NOT drained
        if run.status == "working":
            return run.to_status_dict(now=time.monotonic())      # spurious wake; NOT drained
        return self._result_payload(run)                          # terminal -> drains

    def pending_nudge(self) -> list[AgentRun]:
        return [r for r in self._runs.values()
                if r.generation == self._current_generation
                and r.status in ("done", "error") and not r.drained and not r.nudged]

    def mark_nudged(self, runs: list[AgentRun]) -> None:
        for r in runs:
            r.nudged = True

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
