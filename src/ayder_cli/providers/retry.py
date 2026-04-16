"""Retry wrapper for AIProvider — exponential backoff with jitter + mid-stream recovery."""
from __future__ import annotations

import asyncio
import enum
import logging
import random
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Callable, Dict, Iterable, List, Optional

from ayder_cli.providers.base import AIProvider, NormalizedStreamChunk

logger = logging.getLogger(__name__)


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


def _is_meaningful(chunk: NormalizedStreamChunk) -> bool:
    """A chunk counts as meaningful (point-of-no-return for retries) if it
    carries content, reasoning, or tool-call deltas. Usage-only chunks are
    NOT meaningful — an empty-response stream consists entirely of them."""
    return bool(chunk.content) or bool(chunk.reasoning) or bool(chunk.tool_calls)


class RetryingProvider(AIProvider):
    """Decorator that wraps an inner AIProvider with retry + empty-response
    recovery. Transparent w.r.t. chat / list_models.

    Retry invariant: we only retry while no meaningful chunk has been emitted
    to the outer consumer. Once a meaningful chunk passes through, the stream
    is committed and subsequent errors propagate unchanged.
    """

    def __init__(
        self,
        inner: AIProvider,
        retry_config: RetryConfig,
        *,
        on_reconnect: Optional[Callable[[], None]] = None,
        sleep: Callable[[float], Any] = asyncio.sleep,
    ) -> None:
        # Deliberately bypass AIProvider.__init__ — we delegate to `inner`.
        self._inner = inner
        self._retry = retry_config
        self._on_reconnect = on_reconnect
        self._sleep = sleep

    async def list_models(self) -> List[str]:
        return await self._inner.list_models()

    async def chat(self, *args, **kwargs) -> NormalizedStreamChunk:
        return await self._inner.chat(*args, **kwargs)

    async def stream_with_tools(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        options: Optional[Dict[str, Any]] = None,
        verbose: bool = False,
    ) -> AsyncGenerator[NormalizedStreamChunk, None]:
        if not self._retry.enabled:
            async for chunk in self._inner.stream_with_tools(
                messages, model, tools=tools, options=options, verbose=verbose
            ):
                yield chunk
            return

        last_error: Optional[BaseException] = None
        for attempt in range(self._retry.max_attempts):
            committed = False  # once True, subsequent errors must propagate
            try:
                async for chunk in self._inner.stream_with_tools(
                    messages, model, tools=tools, options=options, verbose=verbose
                ):
                    if not committed and _is_meaningful(chunk):
                        committed = True
                    yield chunk
                # Stream finished cleanly.
                return
            except BaseException as exc:  # noqa: BLE001 — we re-classify below
                if committed:
                    # Point of no return — cannot replay after emitting data.
                    raise
                verdict = classify_error(exc, self._retry.retry_on_names)
                if verdict is RetryVerdict.FATAL:
                    raise
                last_error = exc
                remaining = self._retry.max_attempts - attempt - 1
                if remaining <= 0:
                    logger.warning(
                        f"Provider retry budget exhausted after {attempt + 1} "
                        f"attempts; raising {type(exc).__name__}: {exc}"
                    )
                    raise
                delay = compute_delay(self._retry, attempt)
                logger.info(
                    f"Provider stream failed ({type(exc).__name__}: {exc}); "
                    f"retrying in {delay:.2f}s ({remaining} attempts left)"
                )
                await self._sleep(delay)
                if self._on_reconnect is not None:
                    try:
                        self._on_reconnect()
                    except Exception as hook_exc:  # noqa: BLE001
                        logger.debug(f"on_reconnect hook raised: {hook_exc}")
                continue

        if last_error is not None:
            raise last_error
