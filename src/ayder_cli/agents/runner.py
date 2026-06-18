"""AgentRunner — wraps one ChatLoop execution per agent dispatch.

Disposable: one instance per dispatch. Creates an isolated runtime,
runs a ChatLoop, and produces an AgentRunOutcome.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from ayder_cli.agents.callbacks import AgentCallbacks
from ayder_cli.agents.config import AgentConfig
from ayder_cli.application.runtime_factory import create_agent_runtime
from ayder_cli.loops.chat_loop import ChatLoop, ChatLoopConfig

logger = logging.getLogger(__name__)


@dataclass
class AgentRunOutcome:
    """What an AgentRunner produces; the registry applies it to its AgentRun."""
    status: str          # "done" | "error"
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
        timeout: int = 300,
        run_id: int = 0,
        generation: int = 0,
        on_progress: Callable[[int, str, str, Any], None] | None = None,
    ) -> None:
        self._agent_config = agent_config
        self._parent_config = parent_config
        self._project_ctx = project_ctx
        self._process_manager = process_manager
        self._permissions = permissions
        self._timeout = timeout
        self.run_id = run_id
        self._generation = generation
        self._on_progress = on_progress
        self._cancel_event = asyncio.Event()
        self.status: str = "idle"

    @property
    def agent_name(self) -> str:
        return self._agent_config.name

    def cancel(self) -> bool:
        """Cancel the running agent."""
        logger.debug("cancel requested: agent='%s' run_id=%d", self.agent_name, self.run_id)
        self._cancel_event.set()
        self.status = "cancelled"
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

    def _persist_note(self, task: str, status: str, content: str, error: str | None) -> str | None:
        from ayder_cli.tools.builtins.notes import write_agent_note
        return write_agent_note(
            self._project_ctx, agent_name=self.agent_name, run_id=self.run_id,
            generation=self._generation, status=status, task=task, content=content,
            timestamp=datetime.now().strftime("%Y%m%d-%H%M%S"), error=error,
        )

    async def run(self, task: str) -> AgentRunOutcome:
        """Execute the agent task and return an AgentRunOutcome."""
        self.status = "running"
        task_preview = task[:120] + "..." if len(task) > 120 else task
        logger.debug(
            "run started: agent='%s' run_id=%d model='%s' timeout=%ds task='%s'",
            self.agent_name, self.run_id,
            self._agent_config.model or "(default)",
            self._timeout, task_preview,
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
                tool_tags=frozenset(rt.config.tool_tags) if getattr(rt.config, "tool_tags", None) else None,
                max_history=getattr(rt.config, "max_history_messages", 30),
            )

            chat_loop = ChatLoop(
                llm=rt.llm_provider,
                registry=rt.tool_registry,
                messages=messages,
                config=loop_config,
                callbacks=callbacks,
                context_manager=rt.context_manager,
            )

            try:
                await asyncio.wait_for(
                    chat_loop.run(),
                    timeout=self._timeout,
                )
            except asyncio.TimeoutError:
                self._cancel_event.set()
                self.status = "timeout"
                content = self._final_message(messages) or "Agent timed out before producing output."
                err = f"Agent exceeded {self._timeout}s timeout"
                logger.debug(
                    "run timeout: agent='%s' run_id=%d after %ds",
                    self.agent_name, self.run_id, self._timeout,
                )
                return AgentRunOutcome("error", content, err, self._persist_note(task, "error", content, err))

            # ChatLoop swallows stream/tool failures via on_system_message
            # and returns normally. Promote any captured error into a real
            # error AgentRunOutcome so callers see the cause.
            if callbacks.last_system_error:
                self.status = "error"
                logger.debug(
                    "run failed (captured via on_system_message): agent='%s' run_id=%d error='%s'",
                    self.agent_name, self.run_id, callbacks.last_system_error[:200],
                )
                content = self._final_message(messages)
                err = callbacks.last_system_error
                return AgentRunOutcome("error", content, err, self._persist_note(task, "error", content, err))

            # Completed successfully
            self.status = "completed"
            content = self._final_message(messages) or "Agent completed without producing output."
            logger.debug(
                "run completed: agent='%s' run_id=%d",
                self.agent_name, self.run_id,
            )
            return AgentRunOutcome("done", content, None, self._persist_note(task, "done", content, None))

        except Exception as e:
            self.status = "error"
            logger.exception(f"Agent '{self.agent_name}' failed: {e}")
            return AgentRunOutcome("error", "Agent encountered an error.", str(e),
                                   self._persist_note(task, "error", "Agent encountered an error.", str(e)))
