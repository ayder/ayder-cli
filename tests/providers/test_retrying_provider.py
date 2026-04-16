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
