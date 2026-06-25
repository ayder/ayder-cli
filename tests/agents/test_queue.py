"""Phase (b): concurrency cap queues overflow."""

import asyncio

import pytest

from ayder_cli.agents.registry import _RUNAWAY_CEILING, AgentRegistry
from ayder_cli.agents.runner import AgentRunOutcome

# The pydantic validator caps max_concurrent_agents at 20 (core/config.py); the
# hard runaway ceiling MUST sit above that so queueing still engages at the
# configured maximum (review finding #2).
_CONFIG_MAX_CONCURRENT = 20


class _Cfg:
    model = "test-model"
    system_prompt = "x"


def _registry(cap):
    return AgentRegistry(
        agents={"coder": _Cfg()},
        parent_config=_Cfg(),
        project_ctx=None,
        process_manager=None,
        permissions={"r"},
        agent_timeout=30,
        max_concurrent_agents=cap,
    )


def _fake_runner(events):
    class _R:
        def __init__(self, *a, **k):
            self.agent_name = "coder"
            self.status = "idle"

        def cancel(self):
            self.status = "cancelled"
            return True

        async def run(self, task):
            events["live"] += 1
            events["peak"] = max(events["peak"], events["live"])
            events["ran"].append(task)
            await events["gate"].wait()
            events["live"] -= 1
            return AgentRunOutcome("done", "ok", None, None)

    return _R


@pytest.mark.asyncio
async def test_never_exceeds_cap_others_queue(monkeypatch):
    reg = _registry(2)
    reg.set_loop(asyncio.get_running_loop())
    ev = {"live": 0, "peak": 0, "ran": [], "gate": asyncio.Event()}
    monkeypatch.setattr("ayder_cli.agents.registry.AgentRunner", _fake_runner(ev))

    ids = [reg.create_run("coder", f"t{i}") for i in range(5)]
    assert all(isinstance(i, int) for i in ids)
    await asyncio.sleep(0.05)
    st = {r["run_id"]: r["status"] for r in reg.snapshot()}
    assert sum(1 for s in st.values() if s == "working") <= 2
    assert sum(1 for s in st.values() if s == "queued") >= 3

    ev["gate"].set()
    for rid in ids:
        await reg.await_run(rid, timeout_s=5)
    assert ev["peak"] <= 2
    assert all(reg._runs[rid].status == "done" for rid in ids)


@pytest.mark.asyncio
async def test_read_result_on_queued_does_not_drain(monkeypatch):
    reg = _registry(1)
    reg.set_loop(asyncio.get_running_loop())
    ev = {"live": 0, "peak": 0, "ran": [], "gate": asyncio.Event()}
    monkeypatch.setattr("ayder_cli.agents.registry.AgentRunner", _fake_runner(ev))

    reg.create_run("coder", "first")
    rid2 = reg.create_run("coder", "second")
    await asyncio.sleep(0.05)
    r = reg.read_result(rid2)
    assert r["status"] == "queued"
    assert reg._runs[rid2].drained is False
    ev["gate"].set()
    await reg.await_run(rid2, timeout_s=5)
    assert reg._runs[rid2].status == "done"


@pytest.mark.asyncio
async def test_queued_run_has_no_runner_until_slot_frees(monkeypatch):
    # After the refactor, the AgentRunner is built inside _run_and_queue once a
    # slot frees — so a queued run must NOT yet appear in registry._active.
    reg = _registry(1)
    reg.set_loop(asyncio.get_running_loop())
    ev = {"live": 0, "peak": 0, "ran": [], "gate": asyncio.Event()}
    monkeypatch.setattr("ayder_cli.agents.registry.AgentRunner", _fake_runner(ev))

    reg.create_run("coder", "first")           # takes the only slot
    rid2 = reg.create_run("coder", "second")   # queued
    await asyncio.sleep(0.05)
    assert reg._runs[rid2].status == "queued"
    assert rid2 not in reg._active             # no runner while queued

    ev["gate"].set()
    for rid in list(reg._runs):
        await reg.await_run(rid, timeout_s=5)
    assert reg._runs[rid2].status == "done"


@pytest.mark.asyncio
async def test_cancel_queued_run_skips_execution(monkeypatch):
    reg = _registry(1)
    reg.set_loop(asyncio.get_running_loop())
    ev = {"live": 0, "peak": 0, "ran": [], "gate": asyncio.Event()}
    monkeypatch.setattr("ayder_cli.agents.registry.AgentRunner", _fake_runner(ev))

    rid1 = reg.create_run("coder", "first")
    rid2 = reg.create_run("coder", "second")
    await asyncio.sleep(0.05)
    assert reg._runs[rid2].status == "queued"
    reg.cancel("coder")
    ev["gate"].set()
    await reg.await_run(rid1, timeout_s=5)
    await reg.await_run(rid2, timeout_s=5)
    assert reg._runs[rid2].status == "cancelled"
    assert "second" not in ev["ran"]


@pytest.mark.asyncio
async def test_runaway_ceiling_rejects_overdispatch(monkeypatch):
    reg = _registry(2)
    reg.set_loop(asyncio.get_running_loop())

    class _Blocked:
        def __init__(self, *a, **k):
            self.agent_name = "coder"
            self.status = "idle"

        def cancel(self):
            self.status = "cancelled"
            return True

        async def run(self, task):
            await asyncio.Event().wait()
            return AgentRunOutcome("done", "ok", None, None)

    monkeypatch.setattr("ayder_cli.agents.registry.AgentRunner", _Blocked)
    # Dispatch past the ceiling; exactly _RUNAWAY_CEILING get run ids, the rest
    # are rejected. Robust to the ceiling value.
    results = [reg.create_run("coder", f"t{i}") for i in range(_RUNAWAY_CEILING + 5)]
    ints = [r for r in results if isinstance(r, int)]
    errs = [r for r in results if isinstance(r, str) and "ceiling" in r.lower()]
    assert len(ints) == _RUNAWAY_CEILING
    assert len(errs) == 5


@pytest.mark.asyncio
async def test_queue_engages_at_configured_max(monkeypatch):
    # With the cap at the config maximum, dispatching one over the cap must QUEUE
    # the extra (not hit the runaway ceiling) — so the ceiling must exceed the max.
    assert _RUNAWAY_CEILING > _CONFIG_MAX_CONCURRENT
    reg = _registry(_CONFIG_MAX_CONCURRENT)
    reg.set_loop(asyncio.get_running_loop())
    ev = {"live": 0, "peak": 0, "ran": [], "gate": asyncio.Event()}
    monkeypatch.setattr("ayder_cli.agents.registry.AgentRunner", _fake_runner(ev))

    ids = [reg.create_run("coder", f"t{i}") for i in range(_CONFIG_MAX_CONCURRENT + 1)]
    assert all(isinstance(i, int) for i in ids)  # none rejected by the ceiling
    await asyncio.sleep(0.05)
    statuses = [r["status"] for r in reg.snapshot()]
    assert statuses.count("queued") >= 1  # the overflow run is queued behind the cap
    assert statuses.count("working") <= _CONFIG_MAX_CONCURRENT
    ev["gate"].set()
    for rid in ids:
        await reg.await_run(rid, timeout_s=5)


@pytest.mark.asyncio
async def test_await_run_blocks_through_queue_until_done(monkeypatch):
    # await_run on a still-QUEUED run must treat it as pending: time out while
    # queued, then block through the queue to completion once a slot frees
    # (guards the queued-as-pending fix in await_run).
    reg = _registry(1)
    reg.set_loop(asyncio.get_running_loop())
    ev = {"live": 0, "peak": 0, "ran": [], "gate": asyncio.Event()}
    monkeypatch.setattr("ayder_cli.agents.registry.AgentRunner", _fake_runner(ev))

    reg.create_run("coder", "first")           # occupies the single slot, blocks on gate
    rid2 = reg.create_run("coder", "second")   # queued behind it
    await asyncio.sleep(0.05)
    assert reg._runs[rid2].status == "queued"

    pending = await reg.await_run(rid2, timeout_s=0.05)  # short wait: still queued
    assert pending["status"] in ("queued", "working")
    assert reg._runs[rid2].drained is False

    ev["gate"].set()                            # free the slot
    done = await reg.await_run(rid2, timeout_s=5)
    assert done["status"] == "done"
    assert "second" in ev["ran"]                # it executed only after the slot freed
