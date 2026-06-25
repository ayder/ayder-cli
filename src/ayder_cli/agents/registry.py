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
import os
import time
from typing import Any, Callable

from ayder_cli.agents.config import AgentConfig
from ayder_cli.agents.run import AgentRun
from ayder_cli.agents.runner import AgentRunner, AgentRunOutcome
from ayder_cli.agents.worktree import (
    add_worktree,
    detect_base_branch,
    is_git_repo,
    remove_worktree,
    slugify_branch,
)
from ayder_cli.core.context import ProjectContext
from ayder_cli.tools.builtins.tasks import list_task_ids, read_task

logger = logging.getLogger(__name__)

_PREVIEW_MAX = 48
# Hard fail-fast backstop on total in-flight (queued + working) runs per
# generation. Must stay ABOVE the max_concurrent_agents validator bound (20,
# core/config.py) so the soft cap queues overflow rather than the ceiling
# rejecting it at the configured maximum.
_RUNAWAY_CEILING = 50


def _preview(task: str) -> str | None:
    """First line of the orchestrator's free-text task, truncated for the panel."""
    if not task or not task.strip():
        return None
    first = task.strip().splitlines()[0].strip()
    return first if len(first) <= _PREVIEW_MAX else first[: _PREVIEW_MAX - 1] + "…"


def _compose_agent_prompt(
    task: str,
    task_meta: tuple[str, str, str] | None,
    branch_name: str | None,
) -> str:
    """Build the agent's user turn from the orchestrator's inputs.

    The agent sees ONLY this string. When the orchestrator passed a task_id we
    embed the resolved task file verbatim (the agent "receives the task file
    itself" instead of relying on the orchestrator to paste it); a branch_name
    becomes a commit directive; the free-text `task` is folded in as the
    orchestrator's own instructions. With neither task_id nor branch_name the
    result is just `task` — byte-identical to the pre-feature behaviour.
    """
    directive = (task or "").strip()
    if task_meta is None and not branch_name:
        return directive

    parts: list[str] = []
    if task_meta is not None:
        canonical_id, rel_path, content = task_meta
        parts.append(
            f"You are assigned {canonical_id}. Implement it per your role and its "
            f"Acceptance Criteria — do not wander outside it."
        )
        parts.append(
            f"## {canonical_id}\n"
            f"_Authoritative spec (source: `{rel_path}`), reproduced in full below._\n\n"
            f"{content.strip()}"
        )
    if branch_name:
        parts.append(
            f"## Branch\nDo ALL of your work on `{branch_name}` and COMMIT it to that "
            f"branch before you finish. Do not switch to or touch any other branch."
        )
    if directive:
        parts.append(
            f"## Orchestrator instructions\n{directive}" if task_meta is not None else directive
        )
    return "\n\n".join(parts)


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
        max_concurrent_agents: int = 5,
        on_progress: Callable[[int, str, str, Any], None] | None = None,
        on_complete: Callable[[int, AgentRun], None] | None = None,
    ) -> None:
        self.agents = agents
        self._parent_config = parent_config
        self._project_ctx = project_ctx
        self._process_manager = process_manager
        self._permissions = permissions
        self._agent_timeout = agent_timeout
        self._max_concurrent = max_concurrent_agents
        self._semaphore = asyncio.Semaphore(max_concurrent_agents)
        self._on_progress = on_progress
        self._on_complete = on_complete
        self._loop: asyncio.AbstractEventLoop | None = None
        self._active: dict[int, AgentRunner] = {}  # run_id -> runner
        self._run_counter: int = 0
        self._runs: dict[int, AgentRun] = {}
        self._current_generation: int = 0
        self._settled: dict[str, str] = {}
        self._session_worktrees: set[str] = set()  # worktrees THIS session created

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
        logger.debug("agent generation -> %d (settled reset; %d run(s) retained)",
                     self._current_generation, len(self._runs))
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
            'Configured specialized agents may be available. Use `agent(action="list")` '
            "to discover exact names before dispatching. Each runs in the background with "
            "its own LLM.",
            "",
            "When the work is a task file under `.ayder/tasks/`, pass its `task_id` (e.g. "
            '`TASK-003`) and a `branch_name` to `agent(action="call", ...)` — the harness '
            "resolves the id, fails fast if it doesn't exist, and hands the agent the task "
            "file itself, so you need not paste the task body into `task`.",
            "",
            "**You pull results — they are not delivered automatically.** "
            '`agent(action="call", name=…, task=…)` returns a run id (and echoes the task '
            'it bound the run to). Use `agent(action="status")` to see what is working/done, '
            'and `agent(action="read_result", run_id=…)` to collect a finished one. To wait '
            'for an agent, call `agent(action="read_result", run_id=…, wait=true, '
            'timeout_s=…)` instead of polling in a loop.',
            "",
            "Every run's status and result carry the `task_id` / `task_preview` they were "
            "dispatched with. Check it against what you asked for: if the deliverable discusses "
            "a different task, the agent wandered — discard it and re-dispatch.",
            "",
            "Each finished run has a best-effort `note_path` to its full saved deliverable; "
            "if a result has scrolled out of context, `read_file` that path instead of "
            "re-dispatching. If you end your turn with results unread, you will be nudged "
            "once to collect them.",
            "",
            "**Rules:** dispatch the same agent multiple times if useful; only use an agent "
            "whose specialty matches; on failure, handle the task yourself.",
        ]

        return "\n".join(lines)

    def create_run(
        self,
        name: str,
        task: str,
        task_id: str | None = None,
        branch_name: str | None = None,
        base_branch: str | None = None,
    ) -> int | str:
        """Create an AgentRun and schedule it. MUST run on the event loop.

        Returns run_id (int) or an error string. When task_id is given it is
        resolved against .ayder/tasks/ and the dispatch FAILS FAST if no such
        task exists; when it resolves, the task file is embedded in the agent's
        prompt so the agent receives the spec itself. branch_name (advisory) is
        folded into the prompt as a commit directive — the harness does not run
        git. Returns run_id (int) or an error string."""
        if name not in self.agents:
            available = ", ".join(sorted(self.agents))
            return (f"Error: Agent '{name}' not found. Available: {available}. "
                    'Use agent(action="list").'
                    if available else
                    "Error: Agent '{name}' not found. No agents configured.".format(name=name))
        if name in self._settled and self._settled[name] in ("error", "timeout"):
            return (f"Error: Agent '{name}' failed in this cycle "
                    f"(status: {self._settled[name]}). Handle the task directly.")

        # Resolve task_id against .ayder/tasks/. Fail fast (no dispatch) if it
        # doesn't exist — the orchestrator referenced a task that isn't there.
        task_meta: tuple[str, str, str] | None = None
        resolved_task_id: str | None = None
        if task_id and task_id.strip():
            task_meta = read_task(self._project_ctx, task_id.strip())
            if task_meta is None:
                known = ", ".join(list_task_ids(self._project_ctx)) or "(none)"
                return (
                    f"Error: task_id '{task_id}' not found in .ayder/tasks/ — '{name}' was "
                    f"NOT dispatched. Existing tasks: {known}. Create the task file first "
                    f"(or fix the id), then re-dispatch."
                )
            resolved_task_id = task_meta[0]

        # The agent's ENTIRE user turn is the composed prompt — it has no other
        # context. Require SOME concrete instruction: a non-empty task or a
        # resolved task_id. A blank dispatch makes the agent reply "I don't have a
        # task assigned yet" after burning a full run, so reject it here.
        if task_meta is None and (not task or not task.strip()):
            return (
                f"Error: empty task — '{name}' was NOT dispatched. Pass a concrete `task` "
                "(what to do, which files/branch, the acceptance criteria) and/or a `task_id` "
                "that resolves to a file in .ayder/tasks/. The agent sees nothing else."
            )

        in_flight = sum(
            1 for r in self._runs.values()
            if r.generation == self._current_generation and r.status in ("queued", "working")
        )
        if in_flight >= _RUNAWAY_CEILING:
            return (
                f"Error: agent runaway ceiling ({_RUNAWAY_CEILING}) reached — {in_flight} "
                "runs already queued/working. Collect results before dispatching more."
            )

        if self._loop is None:
            return "Error: Agent registry not initialized (event loop not set)"

        branch = branch_name.strip() if branch_name and branch_name.strip() else None
        prompt = _compose_agent_prompt(task, task_meta, branch)
        task_preview = _preview(task)

        self._run_counter += 1
        run_id = self._run_counter
        run = AgentRun(run_id=run_id, generation=self._current_generation,
                       agent_name=name, started_at=time.monotonic(), status="queued",
                       task_id=resolved_task_id, branch_name=branch, task_preview=task_preview)
        self._runs[run_id] = run
        logger.debug("agent dispatch: run #%d agent='%s' gen=%d task_id=%s branch=%s",
                     run_id, name, self._current_generation, resolved_task_id or "-", branch or "-")
        asyncio.create_task(self._run_and_queue(run, name, prompt, base_branch))
        return run_id

    async def _run_and_queue(
        self, run: AgentRun, name: str, task: str, base_branch: str | None = None
    ) -> None:
        outcome: AgentRunOutcome | None = None
        worktree_path: str | None = None
        try:
            async with self._semaphore:
                if run.status == "cancelled":
                    outcome = AgentRunOutcome(
                        "cancelled", "Run cancelled before it started.", None, None
                    )
                else:
                    project_ctx = self._project_ctx
                    notes_ctx = self._project_ctx
                    if run.branch_name:
                        repo_root = str(self._project_ctx.root)
                        if not is_git_repo(repo_root):
                            outcome = AgentRunOutcome(
                                "error",
                                "Agent not run: worktree isolation needs a git repository, "
                                f"but '{repo_root}' is not one (or git is unavailable).",
                                "not a git repository", None,
                            )
                        else:
                            slug = slugify_branch(run.branch_name)
                            wt_dir = os.path.join(repo_root, ".ayder", "worktrees", slug)
                            base = base_branch or detect_base_branch(repo_root)
                            try:
                                await asyncio.to_thread(
                                    add_worktree, repo_root, wt_dir, run.branch_name, base
                                )
                            except Exception as e:
                                logger.exception("worktree add failed: run_id=%d", run.run_id)
                                outcome = AgentRunOutcome(
                                    "error", f"Worktree creation failed: {e}",
                                    "worktree add failed", None,
                                )
                            else:
                                worktree_path = wt_dir
                                self._session_worktrees.add(wt_dir)
                                run.worktree_path = wt_dir
                                project_ctx = ProjectContext(wt_dir)
                                # notes_ctx stays the parent so the note survives removal
                    if outcome is None:
                        runner = AgentRunner(
                            agent_config=self.agents[name], parent_config=self._parent_config,
                            project_ctx=project_ctx, notes_ctx=notes_ctx,
                            process_manager=self._process_manager,
                            permissions=self._permissions, timeout=self._agent_timeout,
                            run_id=run.run_id, generation=run.generation,
                            on_progress=self._on_progress,
                        )
                        self._active[run.run_id] = runner
                        run.status = "working"
                        outcome = await runner.run(task)
        except Exception:
            logger.exception("agent run crashed: run_id=%d", run.run_id)
            if outcome is None:
                outcome = AgentRunOutcome(
                    "error", "Agent encountered an error.", "internal error", None
                )
        finally:
            self._active.pop(run.run_id, None)
            if worktree_path is not None:
                try:
                    await asyncio.to_thread(
                        remove_worktree, str(self._project_ctx.root), worktree_path
                    )
                except Exception:
                    logger.exception("worktree cleanup failed: %s", worktree_path)
                finally:
                    self._session_worktrees.discard(worktree_path)
            if outcome is not None:
                run.status = outcome.status
                run.result = outcome.content
                run.error = outcome.error
                run.note_path = outcome.note_path
            run.finished_at = time.monotonic()
            run.done_event.set()
            logger.debug("agent done: run #%d agent='%s' status='%s' %ds",
                         run.run_id, run.agent_name, run.status,
                         run.working_time(now=run.finished_at))
            if run.generation == self._current_generation and outcome is not None:
                self._settled[run.agent_name] = outcome.status
            if self._on_complete is not None:
                try:
                    self._on_complete(run.run_id, run)
                except Exception:
                    logger.exception("on_complete callback failed")

    def run_label(self, run_id: int) -> str | None:
        """The '<prompt> · <task_id>' panel label for a run, or None. Loop-owned read."""
        run = self._runs.get(run_id)
        return run.panel_label() if run is not None else None

    def snapshot(self) -> list[dict]:
        now = time.monotonic()
        runs = [r for r in self._runs.values() if r.generation == self._current_generation]
        runs.sort(key=lambda r: r.run_id, reverse=True)
        return [r.to_status_dict(now=now) for r in runs]

    def _result_payload(self, run: AgentRun) -> dict:
        """Full payload for a TERMINAL run; marks it drained. Never call on a working run."""
        if not run.drained:
            logger.debug("agent result drained: run #%d agent='%s' status='%s'",
                         run.run_id, run.agent_name, run.status)
        run.drained = True
        payload = {"run_id": run.run_id, "name": run.agent_name, "status": run.status,
                   "result": run.result, "note_path": run.note_path,
                   "working_time_s": run.working_time(now=time.monotonic()), "error": run.error}
        if run.task_id:
            payload["task_id"] = run.task_id
        if run.task_preview:
            payload["task_preview"] = run.task_preview
        if run.branch_name:
            payload["branch_name"] = run.branch_name
        if run.worktree_path:
            payload["worktree_path"] = run.worktree_path
        return payload

    def read_result(self, run_id: int) -> dict | None:
        run = self._runs.get(run_id)
        if run is None or run.generation != self._current_generation:
            return None
        if run.status in ("queued", "working"):
            return run.to_status_dict(now=time.monotonic())   # NOT drained (finding 1)
        return self._result_payload(run)                       # terminal -> drains

    async def await_run(self, run_id: int, timeout_s: float) -> dict | None:
        run = self._runs.get(run_id)
        if run is None or run.generation != self._current_generation:
            return None
        if run.status in ("queued", "working"):
            capped = max(0.0, min(float(timeout_s), float(self._agent_timeout)))
            try:
                await asyncio.wait_for(run.done_event.wait(), timeout=capped)
            except asyncio.TimeoutError:
                return run.to_status_dict(now=time.monotonic())  # still pending, NOT drained
        if run.status in ("queued", "working"):
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
        """Cancel running and queued instances of the named agent.

        Working runs are cancelled via their live AgentRunner (in _active);
        queued runs have no runner yet (it is built in _run_and_queue once a
        slot frees), so mark the run record cancelled — _run_and_queue skips it
        when its turn comes."""
        cancelled: list[int] = []
        for rid, runner in list(self._active.items()):
            if runner.agent_name == name:
                runner.cancel()
                cancelled.append(rid)
        for rid, run in self._runs.items():
            if run.agent_name == name and run.status == "queued" and rid not in cancelled:
                run.status = "cancelled"
                cancelled.append(rid)
        if cancelled:
            logger.debug("cancel: agent='%s' cancelled %d instance(s): %s",
                         name, len(cancelled), cancelled)
        else:
            logger.debug("cancel: agent='%s' — no running/queued instances", name)
        return len(cancelled) > 0

    def reset_settled(self) -> None:
        """Clear the settled tracker. Call on new user message cycle."""
        self._settled = {}
