"""AgentRunner — wraps one ChatLoop execution per agent dispatch.

Disposable: one instance per dispatch. Creates an isolated runtime,
runs a ChatLoop, and produces an AgentSummary.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Callable

from ayder_cli.agents.callbacks import AgentCallbacks
from ayder_cli.agents.config import AgentConfig
from ayder_cli.agents.summary import AgentSummary
from ayder_cli.application.runtime_factory import create_agent_runtime
from ayder_cli.loops.chat_loop import ChatLoop, ChatLoopConfig

logger = logging.getLogger(__name__)

_SUMMARY_PATTERN = re.compile(
    r"<agent-summary>\s*(.*?)\s*</agent-summary>", re.DOTALL
)


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
        on_progress: Callable[[str, str, Any], None] | None = None,
    ) -> None:
        self._agent_config = agent_config
        self._parent_config = parent_config
        self._project_ctx = project_ctx
        self._process_manager = process_manager
        self._permissions = permissions
        self._timeout = timeout
        self._on_progress = on_progress
        self._cancel_event = asyncio.Event()
        self.status: str = "idle"

    @property
    def agent_name(self) -> str:
        return self._agent_config.name

    def cancel(self) -> bool:
        """Cancel the running agent."""
        self._cancel_event.set()
        self.status = "cancelled"
        return True

    def _parse_summary(self, content: str) -> str:
        """Extract <agent-summary> block or fall back to full content."""
        match = _SUMMARY_PATTERN.search(content)
        if match:
            return match.group(1).strip()
        return content

    async def run(self, task: str) -> AgentSummary:
        """Execute the agent task and return a summary."""
        self.status = "running"

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
            )

            try:
                await asyncio.wait_for(
                    chat_loop.run(),
                    timeout=self._timeout,
                )
            except asyncio.TimeoutError:
                self._cancel_event.set()
                self.status = "timeout"
                summary_text = self._parse_summary(callbacks.last_content)
                return AgentSummary(
                    agent_name=self.agent_name,
                    status="timeout",
                    summary=summary_text or "Agent timed out before producing output.",
                    error=f"Agent exceeded {self._timeout}s timeout",
                )

            # Completed successfully
            self.status = "completed"
            summary_text = self._parse_summary(callbacks.last_content)
            return AgentSummary(
                agent_name=self.agent_name,
                status="completed",
                summary=summary_text or "Agent completed without producing a summary.",
                error=None,
            )

        except Exception as e:
            self.status = "error"
            logger.exception(f"Agent '{self.agent_name}' failed: {e}")
            return AgentSummary(
                agent_name=self.agent_name,
                status="error",
                summary="Agent encountered an error.",
                error=str(e),
            )
