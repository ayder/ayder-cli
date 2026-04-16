"""KV-cache hit detection via prompt processing timing.

Uses prompt_eval_duration / prompt_eval_count ratio to detect whether
Ollama is reusing its KV-cache prefix or recomputing from scratch.
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from typing import Optional

from loguru import logger


@dataclass
class CacheSample:
    timestamp: float
    prompt_tokens: int
    ns_per_token: float
    hit_ratio: float
    state: str


@dataclass
class CacheStatus:
    hit_ratio: float
    state: str  # "cold", "hot", "warm", "miss"


class CacheMonitor:
    """Tracks prompt processing speed to detect KV-cache hits."""

    def __init__(self):
        self._baseline_ns_per_token: Optional[float] = None
        self._history: deque[CacheSample] = deque(maxlen=50)
        self._last_status: Optional[CacheStatus] = None

    @property
    def last_status(self) -> Optional[CacheStatus]:
        return self._last_status

    def record(self, prompt_eval_count: int, prompt_eval_ns: int) -> CacheStatus:
        """Record a sample and return cache status."""
        ns_per_token = prompt_eval_ns / max(prompt_eval_count, 1)

        if self._baseline_ns_per_token is None:
            self._baseline_ns_per_token = ns_per_token
            status = CacheStatus(hit_ratio=0.0, state="cold")
            self._append_sample(prompt_eval_count, ns_per_token, status)
            return status

        speed_ratio = self._baseline_ns_per_token / max(ns_per_token, 1)

        if speed_ratio > 3.0:
            state = "hot"
        elif speed_ratio > 1.5:
            state = "warm"
        else:
            state = "miss"

        hit_ratio = max(0.0, 1.0 - (ns_per_token / self._baseline_ns_per_token))

        # Detect unexpected invalidation (hot → miss transition means the
        # prefix changed since the last call).
        if self._last_status and self._last_status.state == "hot" and state == "miss":
            logger.warning(
                f"KV-cache invalidated: was {self._history[-1].ns_per_token:.0f} ns/tok, "
                f"now {ns_per_token:.0f} ns/tok. Prefix likely changed."
            )
        elif state == "hot":
            logger.debug(f"KV-cache hot: {hit_ratio:.0%} reuse, {ns_per_token:.0f} ns/tok")

        status = CacheStatus(hit_ratio=hit_ratio, state=state)
        self._append_sample(prompt_eval_count, ns_per_token, status)
        return status

    def reset(self) -> None:
        """Clear baseline and history. Called on model eviction."""
        self._baseline_ns_per_token = None
        self._history.clear()
        self._last_status = None

    def _append_sample(self, prompt_tokens: int, ns_per_token: float, status: CacheStatus):
        self._history.append(CacheSample(
            timestamp=time.monotonic(),
            prompt_tokens=prompt_tokens,
            ns_per_token=ns_per_token,
            hit_ratio=status.hit_ratio,
            state=status.state,
        ))
        self._last_status = status
