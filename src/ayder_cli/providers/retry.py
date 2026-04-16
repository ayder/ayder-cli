"""Retry wrapper for AIProvider — exponential backoff with jitter + mid-stream recovery."""
from __future__ import annotations

import enum
import random
from dataclasses import dataclass, field
from typing import Iterable


class RetryVerdict(enum.Enum):
    RETRYABLE = "retryable"
    FATAL = "fatal"


@dataclass(frozen=True)
class RetryConfig:
    """Config for RetryingProvider. Kept separate from the pydantic
    Config section so retry.py has zero dependencies on core.config."""

    enabled: bool = True
    max_attempts: int = 3
    initial_delay_seconds: float = 0.5
    max_delay_seconds: float = 30.0
    backoff_coefficient: float = 2.0
    jitter: bool = True
    retry_on_names: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.max_attempts <= 0:
            raise ValueError("max_attempts must be positive")
        if self.initial_delay_seconds < 0:
            raise ValueError("initial_delay_seconds must be >= 0")
        if self.max_delay_seconds < self.initial_delay_seconds:
            raise ValueError("max_delay_seconds must be >= initial_delay_seconds")
        if self.backoff_coefficient < 1.0:
            raise ValueError("backoff_coefficient must be >= 1.0")


_RETRYABLE_NAMES: frozenset[tuple[str, str]] = frozenset({
    # httpx — shared by ollama, openai (sync transport), anthropic
    ("httpx", "ConnectError"),
    ("httpx", "ReadError"),
    ("httpx", "ReadTimeout"),
    ("httpx", "RemoteProtocolError"),
    ("httpx", "TransportError"),
    # openai
    ("openai", "APIConnectionError"),
    ("openai", "APITimeoutError"),
    ("openai", "RateLimitError"),
    ("openai", "InternalServerError"),
    # anthropic
    ("anthropic", "APIConnectionError"),
    ("anthropic", "APITimeoutError"),
    ("anthropic", "RateLimitError"),
    ("anthropic", "InternalServerError"),
})


def _match_name(exc: BaseException, extra: Iterable[str]) -> bool:
    """Return True if exc's class (or any ancestor) matches a retryable entry."""
    extra_set = set(extra)
    for cls in type(exc).__mro__:
        mod = getattr(cls, "__module__", "") or ""
        name = getattr(cls, "__name__", "") or ""
        top = mod.split(".", 1)[0] if mod else ""
        if (top, name) in _RETRYABLE_NAMES:
            return True
        if name in extra_set:
            return True
        if f"{top}.{name}" in extra_set:
            return True
    return False


def classify_error(
    exc: BaseException,
    retry_on_names: Iterable[str] = (),
) -> RetryVerdict:
    """Return RETRYABLE if `exc` matches a known transient failure."""
    if _match_name(exc, retry_on_names):
        return RetryVerdict.RETRYABLE
    return RetryVerdict.FATAL


def compute_delay(cfg: RetryConfig, attempt: int) -> float:
    """Exponential backoff with equal jitter.

    attempt 0 → base = initial_delay
    attempt 1 → base = initial_delay * coeff
    base is clamped to max_delay. With jitter, result ∈ [base/2, base].
    """
    base = cfg.initial_delay_seconds * (cfg.backoff_coefficient ** attempt)
    base = min(base, cfg.max_delay_seconds)
    if not cfg.jitter:
        return base
    return random.uniform(base / 2.0, base)
