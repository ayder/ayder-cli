"""The stall timeout of the retry layer (``request_timeout_seconds``).

Kind: new interface. ollama and google wait forever on a silent connection, and
openai/anthropic only give up after 600 s, so a stalled provider hung the turn with no
message. ``RetryingProvider`` now watches the stream: when no chunk arrives within the
configured seconds (before the first chunk, or between chunks) the attempt fails with
``ProviderStallTimeout``, which retries like a transport error until a meaningful chunk
has been delivered.

The providers are fakes whose stream stalls on an event that never fires; nothing
touches the network (environment: local-faked).
"""

from __future__ import annotations

import asyncio

import pytest

from ayder_cli.providers.base import NormalizedStreamChunk
from ayder_cli.providers.retry import (
    ProviderStallTimeout,
    RetryConfig,
    RetryingProvider,
    RetryVerdict,
    classify_error,
)

MSG = [{"role": "user", "content": "hi"}]
STALL = "stall"


class _Inner:
    """One scripted stream per attempt; a ``STALL`` item never returns."""

    def __init__(self, *attempts, pause: float = 0.0):
        self.attempts = list(attempts)
        self.pause = pause
        self.calls = 0

    async def stream_with_tools(self, *args, **kwargs):
        script = self.attempts[min(self.calls, len(self.attempts) - 1)]
        self.calls += 1
        for item in script:
            if item == STALL:
                await asyncio.Event().wait()
            if isinstance(item, BaseException):
                raise item
            if self.pause:
                await asyncio.sleep(self.pause)
            yield NormalizedStreamChunk(content=item)


async def _no_sleep(_delay: float) -> None:
    return None


def _provider(inner, *, timeout: float, enabled: bool = True, attempts: int = 3):
    cfg = RetryConfig(
        enabled=enabled,
        max_attempts=attempts,
        initial_delay_seconds=0,
        max_delay_seconds=0,
        jitter=False,
    )
    return RetryingProvider(inner, cfg, sleep=_no_sleep, request_timeout_seconds=timeout)


async def _drain(provider) -> list[str]:
    return [c.content async for c in provider.stream_with_tools(MSG, "m")]


def test_a_stall_before_the_first_chunk_is_retried_then_raised():
    inner = _Inner([STALL])

    with pytest.raises(ProviderStallTimeout):
        asyncio.run(_drain(_provider(inner, timeout=0.05)))

    assert inner.calls == 3


def test_a_stall_before_the_first_chunk_recovers_on_a_later_attempt():
    inner = _Inner([STALL], ["hello"])

    assert asyncio.run(_drain(_provider(inner, timeout=0.05))) == ["hello"]
    assert inner.calls == 2


def test_a_stall_after_a_meaningful_chunk_raises_at_once():
    inner = _Inner(["partial", STALL])
    seen: list[str] = []

    async def go() -> None:
        async for chunk in _provider(inner, timeout=0.05).stream_with_tools(MSG, "m"):
            seen.append(chunk.content)

    with pytest.raises(ProviderStallTimeout):
        asyncio.run(go())

    assert seen == ["partial"]
    assert inner.calls == 1  # the stream was committed: no retry


def test_chunks_arriving_inside_the_window_complete_the_stream():
    """The timeout is per read, not total: 10 chunks 0.02 s apart (0.2 s) pass a 0.05 s limit."""
    inner = _Inner([str(i) for i in range(10)], pause=0.02)

    got = asyncio.run(_drain(_provider(inner, timeout=0.05)))

    assert got == [str(i) for i in range(10)]
    assert inner.calls == 1


def test_zero_never_fires():
    inner = _Inner([STALL])

    async def go() -> None:
        await asyncio.wait_for(_drain(_provider(inner, timeout=0)), timeout=0.2)

    with pytest.raises(TimeoutError) as caught:
        asyncio.run(go())

    assert not isinstance(caught.value, ProviderStallTimeout)
    assert inner.calls == 1


def test_a_providers_own_timeout_is_neither_relabelled_nor_retried():
    inner = _Inner([TimeoutError("sdk read timeout")])

    with pytest.raises(TimeoutError, match="sdk read timeout") as caught:
        asyncio.run(_drain(_provider(inner, timeout=5)))

    assert not isinstance(caught.value, ProviderStallTimeout)
    assert inner.calls == 1


def test_the_disabled_retry_path_is_guarded_too():
    inner = _Inner([STALL])

    with pytest.raises(ProviderStallTimeout):
        asyncio.run(_drain(_provider(inner, timeout=0.05, enabled=False)))

    assert inner.calls == 1  # retry is off: one attempt


def test_a_stalled_stream_that_finishes_before_the_limit_is_untouched():
    inner = _Inner(["a", "b"])

    assert asyncio.run(_drain(_provider(inner, timeout=5))) == ["a", "b"]


def test_a_stall_is_a_retryable_error():
    assert classify_error(ProviderStallTimeout(1)) is RetryVerdict.RETRYABLE


def test_the_message_names_the_setting_and_the_seconds():
    text = str(ProviderStallTimeout(5))

    assert "5 s" in text
    assert "request_timeout_seconds" in text
    assert isinstance(ProviderStallTimeout(5), TimeoutError)


def test_the_wrapper_defaults_to_no_timeout():
    """Preservation: a RetryingProvider built without the keyword has no watchdog."""
    wrapper = RetryingProvider(_Inner(["a"]), RetryConfig())

    assert wrapper._request_timeout == 0
