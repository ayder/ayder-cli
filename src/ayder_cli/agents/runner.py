"""AgentRunner — wraps one ChatLoop execution per agent dispatch.

Disposable: one instance per dispatch. Creates an isolated runtime,
runs a ChatLoop, and produces an AgentRunOutcome.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from ayder_cli.agents.callbacks import AgentCallbacks
from ayder_cli.agents.config import AgentConfig
from ayder_cli.application.runtime_factory import create_agent_runtime
from ayder_cli.log import get_logger
from ayder_cli.loops.chat_loop import ChatLoop, ChatLoopConfig

logger = get_logger("agent")

# Lines an agent is REQUIRED to emit (the task_id/task_preview echo) or that
# carry no deliverable content (the verdict tag). A response that is only these
# lines is vacuous — the agent did no real work (seen in real runs as empty or
# echo-only deliverables that were nonetheless reported "done").
_ECHO_LINE = re.compile(r"^\s*(task_id|task_preview)\s*:", re.IGNORECASE)
_VERDICT_LINE = re.compile(r"^\s*VERDICT\s*:", re.IGNORECASE)


@dataclass
class AgentRunOutcome:
    """What an AgentRunner produces; the registry applies it to its AgentRun."""
    status: str          # "done" | "error" | "cancelled"
    content: str
    error: str | None
    note_path: str | None


class AgentRunner:
    """Executes a single agent task via ChatLoop."""

    def __init__(
        self,
        agent_config: AgentConfig,
        parent_config: Any,
        project_ctx: Any,
        process_manager: Any,
        permissions: set[str],
        timeout: int = 600,
        run_id: int = 0,
        generation: int = 0,
        on_progress: Callable[[int, str, str, Any], None] | None = None,
        notes_ctx: Any = None,
        session_id: str | None = None,
    ) -> None:
        self._agent_config = agent_config
        self._parent_config = parent_config
        self._project_ctx = project_ctx
        self._notes_ctx = notes_ctx if notes_ctx is not None else project_ctx
        self._process_manager = process_manager
        self._permissions = permissions
        self._timeout = timeout
        self.run_id = run_id
        # Inherited from the parent session, never generated here: an agent's
        # events must tie back to the turn that spawned them (C11b).
        self._session_id = session_id
        self._generation = generation
        self._on_progress = on_progress
        self._cancel_event = asyncio.Event()
        self.status: str = "idle"
        self._cancelled = False  # cancel() was called
        # The task running the turn: a child of the task that awaits it (the registry's run task),
        # so waking the turn never cancels the awaiting task. Set only while the turn runs.
        self._turn_task: asyncio.Task | None = None
        self._wake_requested = False  # task.cancel() was called for this run, at most once

    @property
    def agent_name(self) -> str:
        return self._agent_config.name

    def cancel(self) -> bool:
        """Cancel the running agent.

        Besides setting the flag the loop polls between steps, this wakes the turn: it cancels the
        task running it, so a stream or a tool that is awaiting stops now instead of when it yields
        or the deadline fires. That task is the turn's own, never the one awaiting it, so a cancel
        count the turn left behind (a recovered ``TaskGroup`` failure) cannot be mistaken for the
        awaiting task's own cancellation. The request is made once per run, so a repeated
        ``cancel()`` adds no second one (R8).
        """
        logger.debug("cancel requested: agent='{}' run_id={}", self.agent_name, self.run_id)
        self._cancelled = True
        self._cancel_event.set()
        self.status = "cancelled"
        task = self._turn_task
        if task is not None and not self._wake_requested:
            self._wake_requested = True
            task.cancel()
        return True

    @staticmethod
    def _final_message(messages: list[dict]) -> str:
        """Last assistant message with real text — the deliverable.

        Skips pure <think> blocks and tool-only (empty-content) messages.
        """
        for msg in reversed(messages):
            if msg.get("role") != "assistant":
                continue
            content = (msg.get("content") or "").strip()
            if not content:
                continue
            if content.startswith("<think>") and content.endswith("</think>"):
                continue
            return msg.get("content") or ""
        return ""

    @staticmethod
    def _is_vacuous(content: str) -> bool:
        """True if the deliverable has no substance beyond the mandated
        task_id/task_preview echo and a VERDICT tag (empty, echo-only, or
        verdict-only). Such a run did no real work and must settle 'error'."""
        body = "\n".join(
            ln for ln in (content or "").splitlines()
            if not _ECHO_LINE.match(ln) and not _VERDICT_LINE.match(ln)
        ).strip()
        return not body

    def _persist_note(self, task: str, status: str, content: str, error: str | None) -> str | None:
        from ayder_cli.tools.builtins.notes import write_agent_note
        return write_agent_note(
            self._notes_ctx, agent_name=self.agent_name, run_id=self.run_id,
            generation=self._generation, status=status, task=task, content=content,
            timestamp=datetime.now().strftime("%Y%m%d-%H%M%S"), error=error,
        )

    async def run(self, task: str) -> AgentRunOutcome:
        """Execute the agent task and return an AgentRunOutcome."""
        self.status = "running"
        logger.info(
            "run started: agent='{}' run_id={} model='{}' timeout={}s task_chars={}",
            self.agent_name, self.run_id,
            self._agent_config.model or "(default)",
            self._timeout, len(task),
        )

        try:
            rt = create_agent_runtime(
                agent_config=self._agent_config,
                parent_config=self._parent_config,
                project_ctx=self._project_ctx,
                process_manager=self._process_manager,
                permissions=self._permissions,
            )

            callbacks = AgentCallbacks(
                agent_name=self.agent_name,
                run_id=self.run_id,
                cancel_event=self._cancel_event,
                on_progress=self._on_progress,
            )

            messages = [
                {"role": "system", "content": rt.system_prompt},
                {"role": "user", "content": task},
            ]

            loop_config = ChatLoopConfig(
                model=rt.config.model,
                provider=rt.config.provider,
                num_ctx=rt.config.num_ctx,
                max_output_tokens=rt.config.max_output_tokens,
                stop_sequences=list(rt.config.stop_sequences) if rt.config.stop_sequences else [],
                permissions=self._permissions,
                tool_tags=frozenset(rt.config.tool_tags) if rt.config.tool_tags else None,
                max_history=rt.config.max_history_messages,
                max_iterations=self._agent_config.max_iterations or 0,
                session_id=self._session_id,
                run_id=self.run_id,
            )

            chat_loop = ChatLoop(
                llm=rt.llm_provider,
                registry=rt.tool_registry,
                messages=messages,
                config=loop_config,
                callbacks=callbacks,
                context_manager=rt.context_manager,
            )

            woken = False  # the turn was cancelled by cancel(), or cancel() beat the deadline
            # The turn runs in a task of its own. cancel() wakes that task, not this one, and a
            # cancel count the turn leaves behind lives on it. This task's own cancellation, the
            # parent's, is then the only thing that raises its count above what it was at entry.
            awaiting = asyncio.current_task()
            cancels_at_entry = awaiting.cancelling() if awaiting is not None else 0
            turn = asyncio.ensure_future(chat_loop.run())
            self._turn_task = turn
            try:
                await asyncio.wait_for(turn, timeout=self._timeout)
            except asyncio.TimeoutError:
                if not self._cancelled:
                    self._cancel_event.set()
                    self.status = "timeout"
                    content = self._final_message(messages) or "Agent timed out before producing output."
                    err = (
                        f"Agent FAILED because it exceeded its {self._timeout}s timeout before "
                        f"finishing (not an error in the work, and any partial output above is "
                        f"incomplete). The task needs MORE TIME, not a smaller scope — re-dispatch "
                        f"the same agent with a larger timeout, e.g. "
                        f'agent(action="call", name=..., timeout_s={self._timeout * 2}).'
                    )
                    logger.debug(
                        "run timeout: agent='{}' run_id={} after {}s",
                        self.agent_name, self.run_id, self._timeout,
                    )
                    return AgentRunOutcome("error", content, err, self._persist_note(task, "error", content, err))
                woken = True  # cancel() was called first: the run is cancelled, not timed out
            except asyncio.CancelledError:
                if awaiting is not None and awaiting.cancelling() > cancels_at_entry:
                    raise  # this task was asked to cancel: the parent's request propagates
                if not self._wake_requested:
                    raise  # the turn ended cancelled, and not at this runner's request
                woken = True
            finally:
                self._turn_task = None

            outcome: Any = getattr(chat_loop, "outcome", None)
            turn_status = getattr(outcome, "status", None)

            # The loop reports how its turn ended; read it rather than the text of a message.
            if turn_status == "failed":
                self.status = "error"
                err = outcome.message or ""
                logger.error(
                    "run failed (turn outcome): agent='{}' run_id={} error_chars={}",
                    self.agent_name, self.run_id, len(err),
                )
                content = self._final_message(messages)
                return AgentRunOutcome("error", content, err, self._persist_note(task, "error", content, err))

            # Cancelled by cancel(): not an error, and not nudged (R8).
            if self._cancelled and (woken or turn_status == "cancelled"):
                self.status = "cancelled"
                logger.info(
                    "run cancelled: agent='{}' run_id={}", self.agent_name, self.run_id,
                )
                content = self._final_message(messages) or "Agent cancelled before finishing."
                err = "Agent cancelled by request."
                return AgentRunOutcome(
                    "cancelled", content, err, self._persist_note(task, "cancelled", content, err)
                )

            # Loop returned. A vacuous deliverable (empty / echo-only / verdict-
            # only) means the agent did no real work — settle 'error' so the
            # orchestrator re-dispatches instead of accepting a hollow "done".
            content = self._final_message(messages)
            if self._is_vacuous(content):
                self.status = "error"
                err = "Agent produced no deliverable (empty or echo-only response)."
                logger.error(
                    "run vacuous: agent='{}' run_id={}", self.agent_name, self.run_id,
                )
                body = content or err
                return AgentRunOutcome(
                    "error", body, err, self._persist_note(task, "error", body, err)
                )

            # Completed successfully
            self.status = "completed"
            logger.info(
                "run completed: agent='{}' run_id={}",
                self.agent_name, self.run_id,
            )
            return AgentRunOutcome("done", content, None, self._persist_note(task, "done", content, None))

        except Exception as e:
            self.status = "error"
            logger.exception("Agent '{}' failed", self.agent_name)
            return AgentRunOutcome("error", "Agent encountered an error.", str(e),
                                   self._persist_note(task, "error", "Agent encountered an error.", str(e)))
