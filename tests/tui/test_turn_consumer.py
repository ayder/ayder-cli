"""The turn consumer runs one ChatLoop.run() at a time and awaits teardown on interrupt."""

import asyncio
import contextlib
from unittest.mock import MagicMock
import pytest


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _app(monkeypatch):
    from ayder_cli.tui.app import AyderApp
    app = AyderApp.__new__(AyderApp)
    app._requests = asyncio.Queue()
    app._run_task = None
    app._agent_registry = None
    app.messages = []
    monkeypatch.setattr(app, "_after_turn_finished", lambda: None, raising=False)
    monkeypatch.setattr(app, "_report_turn_error", lambda e: None, raising=False)
    return app


@pytest.mark.anyio
async def test_interrupt_is_serialized(monkeypatch):
    app = _app(monkeypatch)
    order = []
    a_in = asyncio.Event()

    class FakeLoop:
        async def run(self, *, no_tools=False):
            if not a_in.is_set():
                a_in.set()
                order.append("A-start")
                try:
                    await asyncio.sleep(3600)
                finally:
                    order.append("A-exit")
            else:
                order.append("B-start")

    app.chat_loop = FakeLoop()
    engine = asyncio.create_task(app._turn_consumer())
    app.request_turn()                                  # A
    await asyncio.wait_for(a_in.wait(), 1)
    app.request_turn(interrupt=True)                    # B interrupts A
    for _ in range(100):
        await asyncio.sleep(0)
        if order[-1:] == ["B-start"]:
            break
    assert order == ["A-start", "A-exit", "B-start"]    # A fully exits BEFORE B starts
    engine.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await engine


@pytest.mark.anyio
async def test_prepare_runs_only_when_quiescent(monkeypatch):
    app = _app(monkeypatch)
    events = []

    class FakeLoop:
        async def run(self, *, no_tools=False):
            events.append("run")
            await asyncio.sleep(0)

    app.chat_loop = FakeLoop()
    engine = asyncio.create_task(app._turn_consumer())
    app.request_turn(prepare=lambda: events.append("prep1"))
    app.request_turn(prepare=lambda: events.append("prep2"))
    for _ in range(50):
        await asyncio.sleep(0)
        if events.count("run") == 2:
            break
    # each prepare immediately precedes its own run; prepares never interleave a run
    assert events == ["prep1", "run", "prep2", "run"]
    engine.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await engine


@pytest.mark.anyio
async def test_run_loop_false_mutates_without_starting_a_turn(monkeypatch):
    app = _app(monkeypatch)
    ran = []

    class FakeLoop:
        async def run(self, *, no_tools=False):
            ran.append(1)

    app.chat_loop = FakeLoop()
    engine = asyncio.create_task(app._turn_consumer())
    done = []
    app.request_turn(prepare=lambda: done.append("mutated"), run_loop=False)
    for _ in range(50):
        await asyncio.sleep(0)
        if done:
            break
    assert done == ["mutated"] and ran == []     # prepare ran; no ChatLoop.run
    engine.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await engine


@pytest.mark.anyio
async def test_ctrl_c_cancels_active_turn_but_preserves_queue(monkeypatch):
    # finding 4: action_cancel cancels only the active turn; queued requests survive.
    app = _app(monkeypatch)
    monkeypatch.setattr(app, "query_one", lambda *a, **k: MagicMock())
    app._activity_timer = None
    app._cancel_event = None
    started = []
    a_in = asyncio.Event()

    class FakeLoop:
        async def run(self, *, no_tools=False):
            started.append("turn")
            if len(started) == 1:
                a_in.set()
                await asyncio.sleep(3600)        # A blocks until cancelled

    app.chat_loop = FakeLoop()
    engine = asyncio.create_task(app._turn_consumer())
    app.request_turn()                            # A (runs, blocks)
    await asyncio.wait_for(a_in.wait(), 1)
    app.request_turn()                            # B queued behind A
    app.action_cancel()                           # Ctrl+C — must NOT drain B
    for _ in range(100):
        await asyncio.sleep(0)
        if len(started) == 2:
            break
    assert started == ["turn", "turn"]            # B still ran after A was cancelled
    engine.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await engine
