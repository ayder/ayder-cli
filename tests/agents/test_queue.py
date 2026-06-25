"""Phase (b): concurrency cap queues overflow."""

import asyncio

import pytest

from ayder_cli.agents.registry import AgentRegistry
from ayder_cli.agents.runner import AgentRunOutcome


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
    results = [reg.create_run("coder", f"t{i}") for i in range(25)]
    assert any(isinstance(r, str) and "ceiling" in r.lower() for r in results)
