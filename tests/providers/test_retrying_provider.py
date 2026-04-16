"""Behavior tests for RetryingProvider decorator."""
from typing import Any, AsyncGenerator, Dict, List, Optional

import pytest

from ayder_cli.providers.base import (
    AIProvider,
    NormalizedStreamChunk,
)
from ayder_cli.providers.retry import RetryConfig, RetryingProvider


class _FakeProvider(AIProvider):
    """Test double that replays a scripted sequence of streams."""

    def __init__(self, scripts: List[List[Any]]):
        # Each script is a list where entries are either NormalizedStreamChunk
        # instances (to yield) or Exception instances (to raise).
        self._scripts = scripts
        self.calls = 0

    async def chat(self, *args, **kwargs) -> NormalizedStreamChunk:
        raise NotImplementedError

    async def stream_with_tools(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        options: Optional[Dict[str, Any]] = None,
        verbose: bool = False,
    ) -> AsyncGenerator[NormalizedStreamChunk, None]:
        idx = self.calls
        self.calls += 1
        if idx >= len(self._scripts):
            raise RuntimeError(f"No script for attempt {idx}")
        for event in self._scripts[idx]:
            if isinstance(event, BaseException):
                raise event
            yield event


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_happy_path_passes_chunks_through_without_retry():
    chunks = [
        NormalizedStreamChunk(content="hello"),
        NormalizedStreamChunk(content=" world"),
        NormalizedStreamChunk(usage={"total_tokens": 5}),
    ]
    inner = _FakeProvider([chunks])
    retry_cfg = RetryConfig(max_attempts=3, jitter=False, initial_delay_seconds=0.0)
    wrapped = RetryingProvider(inner, retry_cfg)

    got: list[NormalizedStreamChunk] = []
    async for c in wrapped.stream_with_tools(messages=[], model="m"):
        got.append(c)

    assert [g.content for g in got] == ["hello", " world", ""]
    assert got[-1].usage == {"total_tokens": 5}
    assert inner.calls == 1  # no retry


@pytest.mark.anyio
async def test_list_models_delegates_to_inner():
    class _Listable(_FakeProvider):
        async def list_models(self) -> List[str]:
            return ["m1", "m2"]

    inner = _Listable([])
    wrapped = RetryingProvider(inner, RetryConfig())
    assert await wrapped.list_models() == ["m1", "m2"]


async def _noop_sleep(delay: float) -> None:
    """Test helper: swallow sleep calls so tests don't wait."""
    return None


@pytest.mark.anyio
async def test_retryable_error_before_emit_triggers_retry():
    """httpx.ConnectError before any meaningful chunk → retry succeeds."""
    import httpx
    err = httpx.ConnectError("dropped")
    good = [NormalizedStreamChunk(content="ok")]
    inner = _FakeProvider([[err], good])  # attempt 0 raises, attempt 1 succeeds
    retry_cfg = RetryConfig(
        max_attempts=3, initial_delay_seconds=0.0, jitter=False
    )
    wrapped = RetryingProvider(inner, retry_cfg, sleep=_noop_sleep)

    got = [c async for c in wrapped.stream_with_tools(messages=[], model="m")]

    assert [g.content for g in got] == ["ok"]
    assert inner.calls == 2


@pytest.mark.anyio
async def test_fatal_error_raises_without_retry():
    """ValueError is not retryable — propagate immediately."""
    err = ValueError("bad")
    inner = _FakeProvider([[err]])
    retry_cfg = RetryConfig(max_attempts=3, initial_delay_seconds=0.0, jitter=False)
    wrapped = RetryingProvider(inner, retry_cfg, sleep=_noop_sleep)

    with pytest.raises(ValueError, match="bad"):
        async for _ in wrapped.stream_with_tools(messages=[], model="m"):
            pass
    assert inner.calls == 1


@pytest.mark.anyio
async def test_error_after_emit_propagates_without_retry():
    """Once a meaningful chunk has been yielded, errors must NOT retry."""
    import httpx
    err = httpx.ConnectError("mid-stream drop")
    script = [
        NormalizedStreamChunk(content="partial"),  # meaningful — commits stream
        err,
    ]
    inner = _FakeProvider([script, [NormalizedStreamChunk(content="recovered")]])
    retry_cfg = RetryConfig(max_attempts=3, initial_delay_seconds=0.0, jitter=False)
    wrapped = RetryingProvider(inner, retry_cfg, sleep=_noop_sleep)

    received: list[str] = []
    with pytest.raises(httpx.ConnectError):
        async for c in wrapped.stream_with_tools(messages=[], model="m"):
            received.append(c.content)

    assert received == ["partial"]
    assert inner.calls == 1  # did NOT retry


@pytest.mark.anyio
async def test_retry_budget_exhausted_raises_last_error():
    """After max_attempts failures, raise the last exception."""
    import httpx
    errs = [httpx.ConnectError(f"drop-{i}") for i in range(3)]
    inner = _FakeProvider([[errs[0]], [errs[1]], [errs[2]]])
    retry_cfg = RetryConfig(max_attempts=3, initial_delay_seconds=0.0, jitter=False)
    wrapped = RetryingProvider(inner, retry_cfg, sleep=_noop_sleep)

    with pytest.raises(httpx.ConnectError, match="drop-2"):
        async for _ in wrapped.stream_with_tools(messages=[], model="m"):
            pass
    assert inner.calls == 3


@pytest.mark.anyio
async def test_empty_stream_triggers_retry():
    """A stream that closes without emitting a meaningful chunk is treated
    as 'empty response' and retried."""
    empty = [NormalizedStreamChunk(usage={"total_tokens": 0})]
    recovered = [NormalizedStreamChunk(content="finally", usage={"total_tokens": 3})]
    inner = _FakeProvider([empty, recovered])
    retry_cfg = RetryConfig(max_attempts=2, initial_delay_seconds=0.0, jitter=False)
    wrapped = RetryingProvider(inner, retry_cfg, sleep=_noop_sleep)

    got = [c async for c in wrapped.stream_with_tools(messages=[], model="m")]

    assert any(c.content == "finally" for c in got)
    assert inner.calls == 2


@pytest.mark.anyio
async def test_empty_stream_after_budget_yields_final_usage_chunk():
    """If all retries produce empty streams, yield the most recent usage-only
    chunk so token accounting isn't lost, then let the outer consumer handle
    the empty-response message."""
    empty1 = [NormalizedStreamChunk(usage={"total_tokens": 1})]
    empty2 = [NormalizedStreamChunk(usage={"total_tokens": 2})]
    inner = _FakeProvider([empty1, empty2])
    retry_cfg = RetryConfig(max_attempts=2, initial_delay_seconds=0.0, jitter=False)
    wrapped = RetryingProvider(inner, retry_cfg, sleep=_noop_sleep)

    got = [c async for c in wrapped.stream_with_tools(messages=[], model="m")]

    # Final usage from the last attempt must survive.
    assert got, "expected at least one chunk to pass through"
    assert got[-1].usage == {"total_tokens": 2}
    # But no meaningful content / tool_calls.
    assert all(not _meaningful(c) for c in got)
    assert inner.calls == 2


def _meaningful(chunk):
    return bool(chunk.content) or bool(chunk.reasoning) or bool(chunk.tool_calls)
