"""Retry wrapper for AIProvider — exponential backoff with jitter + mid-stream recovery."""
from __future__ import annotations

import asyncio
import enum
import random
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Callable, Dict, Iterable, List, Optional

from ayder_cli.log import get_logger
from ayder_cli.providers.base import AIProvider, NormalizedStreamChunk

logger = get_logger("llm")


class RetryVerdict(enum.Enum):
    RETRYABLE = "retryable"
    FATAL = "fatal"


class ProviderStallTimeout(TimeoutError):
    """The provider sent no chunk for request_timeout_seconds."""

    def __init__(self, seconds: float) -> None:
        self.seconds = seconds
        super().__init__(
            f"the provider sent nothing for {seconds:g} s. Raise "
            "request_timeout_seconds in the [llm.<provider>] profile, or set it "
            "to 0 to remove the timeout."
        )


@dataclass(frozen=True)
class RetryConfig:
    """Config for RetryingProvider. Kept separate from the pydantic
    Config section so retry.py has zero dependencies on core.config."""

    enabled: bool = True
    max_attempts: int = 6
    initial_delay_seconds: float = 10.0
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
    # httpx — ollama's transport
    ("httpx", "ConnectError"),
    ("httpx", "ReadError"),
    ("httpx", "ReadTimeout"),
    ("httpx", "RemoteProtocolError"),
    ("httpx", "TransportError"),
    # httpx2 — openai 3.x and anthropic 2.x transport; raw errors can escape a stream
    ("httpx2", "ConnectError"),
    ("httpx2", "ReadError"),
    ("httpx2", "ReadTimeout"),
    ("httpx2", "RemoteProtocolError"),
    ("httpx2", "TransportError"),
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
    # google-genai — 5xx (503 "high demand"); a 429 ClientError is matched in
    # classify_error. The SDK itself does not retry (retry_options=None).
    ("google", "ServerError"),
    # ollama — covers bare "EOF (status code: -1)" mid-stream (transport
    # drop, server crash, OOM kill) and other transient server failures.
    # The committed=False gate above ensures we never retry after content
    # has been yielded to the chat loop.
    ("ollama", "ResponseError"),
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
    if isinstance(exc, ProviderStallTimeout):
        return RetryVerdict.RETRYABLE
    if _match_name(exc, retry_on_names):
        return RetryVerdict.RETRYABLE
    # google-genai raises one ClientError class for every 4xx; only 429 is transient.
    # By name and module, so retry.py does not import google-genai.
    if (
        type(exc).__name__ == "ClientError"
        and type(exc).__module__.startswith("google.genai")
        and getattr(exc, "code", None) == 429
    ):
        return RetryVerdict.RETRYABLE
    # The native Qwen driver raises one error for every non-200 status; 429 and 5xx are
    # transient, anything else is not. Matched by name and module, like Gemini's 429.
    if (
        type(exc).__name__ == "QwenStreamError"
        and type(exc).__module__ == "ayder_cli.providers.impl.qwen"
    ):
        status = getattr(exc, "status_code", None)
        if isinstance(status, int) and (status == 429 or 500 <= status <= 599):
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


async def _stall_guarded(
    stream: AsyncGenerator[NormalizedStreamChunk, None], seconds: float
) -> AsyncGenerator[NormalizedStreamChunk, None]:
    """Yield from `stream`; raise ProviderStallTimeout when no chunk arrives
    within `seconds` (time to the first chunk, then between chunks). 0 = off."""
    if seconds <= 0:
        async for chunk in stream:
            yield chunk
        return
    iterator = stream.__aiter__()
    try:
        while True:
            guard = asyncio.timeout(seconds)
            try:
                async with guard:
                    chunk = await anext(iterator)
            except StopAsyncIteration:
                return
            except TimeoutError:
                if guard.expired():
                    raise ProviderStallTimeout(seconds) from None
                raise  # the provider's own TimeoutError: not ours to relabel
            yield chunk
    finally:
        aclose = getattr(iterator, "aclose", None)
        if aclose is not None:
            await aclose()


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
        request_timeout_seconds: float = 0.0,
    ) -> None:
        # Deliberately bypass AIProvider.__init__ — we delegate to `inner`.
        self._inner = inner
        self._request_timeout = request_timeout_seconds
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
            async for chunk in _stall_guarded(
                self._inner.stream_with_tools(
                    messages, model, tools=tools, options=options, verbose=verbose
                ),
                self._request_timeout,
            ):
                yield chunk
            return

        last_error: Optional[BaseException] = None
        for attempt in range(self._retry.max_attempts):
            committed = False
            usage_only_this_attempt: List[NormalizedStreamChunk] = []
            try:
                async for chunk in _stall_guarded(
                    self._inner.stream_with_tools(
                        messages, model, tools=tools, options=options, verbose=verbose
                    ),
                    self._request_timeout,
                ):
                    if _is_meaningful(chunk):
                        committed = True
                        # Flush any usage-only prelude from this attempt first,
                        # then yield the meaningful chunk.
                        for pending in usage_only_this_attempt:
                            yield pending
                        usage_only_this_attempt = []
                        yield chunk
                    else:
                        if committed:
                            yield chunk
                        else:
                            usage_only_this_attempt.append(chunk)

                if committed:
                    return  # stream committed and completed cleanly

                # Attempt produced no meaningful chunks — treat as empty response.
                remaining = self._retry.max_attempts - attempt - 1
                if remaining <= 0:
                    logger.warning(
                        "Provider returned empty response after "
                        "{} attempts; yielding final usage-only chunk",
                        attempt + 1,
                    )
                    # Yield the final usage-only chunk so token accounting survives.
                    if usage_only_this_attempt:
                        yield usage_only_this_attempt[-1]
                    return
                delay = compute_delay(self._retry, attempt)
                logger.info(
                    "Empty response from provider; retrying in {:.2f}s "
                    "({} attempts left)",
                    delay, remaining,
                )
                await self._sleep(delay)
                if self._on_reconnect is not None:
                    try:
                        self._on_reconnect()
                    except Exception:  # noqa: BLE001 - reconnect boundary: user-supplied on_reconnect hook must not abort the retry
                        logger.opt(exception=True).warning("on_reconnect hook raised")
                continue

            except Exception as exc:  # noqa: BLE001 — we re-classify below
                logger.opt(exception=True).debug("Provider stream raised; evaluating retry")
                if committed:
                    raise
                verdict = classify_error(exc, self._retry.retry_on_names)
                if verdict is RetryVerdict.FATAL:
                    raise
                last_error = exc
                remaining = self._retry.max_attempts - attempt - 1
                if remaining <= 0:
                    logger.warning(
                        "Provider retry budget exhausted after {} "
                        "attempts; raising {}",
                        attempt + 1, type(exc).__name__,
                    )
                    raise
                delay = compute_delay(self._retry, attempt)
                logger.info(
                    "Provider stream failed ({}); "
                    "retrying in {:.2f}s ({} attempts left)",
                    type(exc).__name__, delay, remaining,
                )
                await self._sleep(delay)
                if self._on_reconnect is not None:
                    try:
                        self._on_reconnect()
                    except Exception:  # noqa: BLE001 - reconnect boundary: user-supplied on_reconnect hook must not abort the retry
                        logger.opt(exception=True).warning("on_reconnect hook raised")
                continue

        if last_error is not None:
            raise last_error
