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
    status: str = "working"                 # "working" | "done" | "error"
    result: str = ""                        # final message; "" until finished
    error: str | None = None
    note_path: str | None = None
    finished_at: float | None = None
    drained: bool = False
    nudged: bool = False
    done_event: asyncio.Event = field(default_factory=asyncio.Event)

    def working_time(self, *, now: float) -> int:
        return int((self.finished_at if self.finished_at is not None else now) - self.started_at)

    @property
    def has_unread_result(self) -> bool:
        return self.status in ("done", "error") and not self.drained

    def to_status_dict(self, *, now: float) -> dict:
        return {
            "run_id": self.run_id, "name": self.agent_name, "status": self.status,
            "working_time_s": self.working_time(now=now),
            "has_unread_result": self.has_unread_result, "note_path": self.note_path,
        }
