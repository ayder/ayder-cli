"""Temporal worker runtime entry service."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from ayder_cli.services.temporal_client import TemporalClientAdapter, TemporalClientUnavailableError


@dataclass
class TemporalWorkerConfig:
    """Configuration for a temporal worker session."""

    queue_name: str
    prompt_path: str | None
    permissions: set[str]
    iterations: int
    poll_interval_seconds: float = 0.25
    max_loops: int | None = None


class TemporalWorker:
    """Long-running temporal worker loop with graceful shutdown."""

    def __init__(
        self,
        config: TemporalWorkerConfig,
        client_adapter: TemporalClientAdapter | None = None,
    ) -> None:
        self.config = config
        self._client_adapter = client_adapter or TemporalClientAdapter()
        self._stop_event = asyncio.Event()

    def stop(self) -> None:
        """Request worker shutdown."""
        self._stop_event.set()

    async def run_async(self) -> int:
        """Run worker polling loop until stopped."""
        try:
            self._client_adapter.get_client()
        except TemporalClientUnavailableError as e:
            print(f"Temporal worker startup failed: {e}")
            return 1

        prompt_info = self.config.prompt_path or "<default>"
        perms = ",".join(sorted(self.config.permissions))
        print(
            "Temporal worker running "
            f"(queue={self.config.queue_name}, prompt={prompt_info}, permissions={perms})"
        )

        loops = 0
        while not self._stop_event.is_set():
            loops += 1
            await asyncio.sleep(self.config.poll_interval_seconds)
            if self.config.max_loops is not None and loops >= self.config.max_loops:
                break

        print("Temporal worker stopped")
        return 0

    def run(self) -> int:
        """Run worker loop in sync context with Ctrl+C handling."""
        try:
            return asyncio.run(self.run_async())
        except KeyboardInterrupt:
            print("Temporal worker interrupted by user")
            return 0
