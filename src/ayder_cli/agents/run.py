"""AgentRun — the per-dispatch state record the main LLM polls and drains."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field


@dataclass
class AgentRun:
    run_id: int
    generation: int
    agent_name: str
    started_at: float                       # monotonic() at dispatch
    status: str = "working"                 # "queued" | "working" | "done" | "error" | "cancelled"
    result: str = ""                        # final message; "" until finished
    error: str | None = None
    note_path: str | None = None
    task_id: str | None = None              # canonical "TASK-NNN" this run implements, if any
    branch_name: str | None = None          # git branch the agent was told to work/commit on
    task_preview: str | None = None         # short preview of the orchestrator's free-text task
    finished_at: float | None = None
    drained: bool = False
    nudged: bool = False
    done_event: asyncio.Event = field(default_factory=asyncio.Event)

    def working_time(self, *, now: float) -> int:
        return int((self.finished_at if self.finished_at is not None else now) - self.started_at)

    def panel_label(self) -> str | None:
        """Short '<prompt> · <task_id>' label for the agent panel status line.

        Returns the free-text preview and/or the task id (whichever the dispatch
        carried), or None when neither is set."""
        bits = [b for b in (self.task_preview, self.task_id) if b]
        return " · ".join(bits) if bits else None

    @property
    def has_unread_result(self) -> bool:
        return self.status in ("done", "error") and not self.drained

    def to_status_dict(self, *, now: float) -> dict:
        d = {
            "run_id": self.run_id, "name": self.agent_name, "status": self.status,
            "working_time_s": self.working_time(now=now),
            "has_unread_result": self.has_unread_result, "note_path": self.note_path,
        }
        # Assignment metadata only when the dispatch carried it — keeps the common
        # (no task_id / no branch) status output unchanged. task_preview lets the
        # orchestrator correlate a run with what it dispatched even for free-text
        # tasks (no task_id), so a wandering agent's result is obvious at a glance.
        if self.task_id:
            d["task_id"] = self.task_id
        if self.task_preview:
            d["task_preview"] = self.task_preview
        if self.branch_name:
            d["branch_name"] = self.branch_name
        return d
