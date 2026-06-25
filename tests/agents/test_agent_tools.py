"""Tests for the consolidated agent(action=...) dispatcher."""

import asyncio
import json
from unittest.mock import MagicMock

import pytest

from ayder_cli.agents.tool import create_agent_handler


def test_call_return_leads_with_run_id():
    reg = MagicMock()
    reg._on_loop.side_effect = lambda fn: fn()
    reg.create_run.return_value = 7
    reg.run_label.return_value = None
    out = create_agent_handler(reg)(action="call", name="reviewer", task="do it")
    assert "run #7" in out and "read_result" in out


def test_status_returns_snapshot_json():
    reg = MagicMock()
    reg._on_loop.side_effect = lambda fn: fn()
    reg.snapshot.return_value = [
        {
            "run_id": 7,
            "name": "r",
            "status": "done",
            "working_time_s": 1,
            "has_unread_result": True,
            "note_path": None,
        }
    ]
    data = json.loads(create_agent_handler(reg)(action="status"))
    assert data["agents"][0]["run_id"] == 7
    assert "result" not in data["agents"][0]


def test_list_marshals_through_loop():
    # finding 3: list_agents reads _active/_settled, so it must go through _on_loop.
    reg = MagicMock()
    reg.list_agents.return_value = [{"name": "r"}]
    calls = []
    reg._on_loop.side_effect = lambda fn: (calls.append("on_loop"), fn())[1]
    data = json.loads(create_agent_handler(reg)(action="list"))
    assert calls == ["on_loop"]                 # marshalled, not a direct read
    assert data["agents"][0]["name"] == "r"


@pytest.mark.asyncio
async def test_read_result_wait_blocks_then_returns():
    reg = MagicMock()
    reg._loop = asyncio.get_running_loop()

    async def _await_run(run_id, timeout_s):
        return {"run_id": run_id, "result": "DONE"}

    reg.await_run = _await_run
    out = await asyncio.to_thread(
        create_agent_handler(reg), action="read_result", run_id=3, wait=True, timeout_s=5
    )
    assert json.loads(out)["result"] == "DONE"


def test_cli_registers_pull_tools(monkeypatch):
    import ayder_cli.cli_runner as cli
    registered = []
    fake_reg = MagicMock()
    fake_reg.get_capability_prompts.return_value = ""
    fake_registry_obj = MagicMock()
    fake_registry_obj.register_dynamic_tool = lambda defn, h: registered.append(defn.name)
    rt = MagicMock()
    rt.config = MagicMock(agents={"r": object()}, model="m", provider="p", num_ctx=1,
                          max_output_tokens=1, stop_sequences=[], tool_tags=None, max_history_messages=30,
                          verbose=False)
    rt.tool_registry = fake_registry_obj
    monkeypatch.setattr(cli, "create_runtime", lambda **k: rt)
    monkeypatch.setattr(cli, "AgentRegistry", lambda **k: fake_reg)
    monkeypatch.setattr(cli, "ChatLoop", MagicMock())
    monkeypatch.setattr(cli.asyncio, "run", lambda coro: coro.close())
    cli._run_loop("hi", permissions={"r"})
    assert {"agent"} <= set(registered)
    assert {"call_agent", "list_agents", "agent_status", "read_agent_result"}.isdisjoint(registered)
