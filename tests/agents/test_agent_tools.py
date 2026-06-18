"""Tests for the new pull tools: agent_status, read_agent_result, list_agents marshalling."""

import asyncio
import json
import pytest
from unittest.mock import MagicMock

from ayder_cli.agents.run import AgentRun
from ayder_cli.agents.tool import (
    create_call_agent_handler, create_agent_status_handler, create_read_agent_result_handler,
)


def _reg_on_loop(reg):
    reg._on_loop = lambda fn: fn()  # synchronous for unit tests


def test_call_agent_return_leads_with_run_id():
    reg = MagicMock()
    reg.create_run.return_value = 7
    _reg_on_loop(reg)
    out = create_call_agent_handler(reg)(name="reviewer", task="do it")
    assert "run #7" in out and "read_agent_result" in out


def test_agent_status_returns_snapshot_json():
    reg = MagicMock()
    reg.snapshot.return_value = [{"run_id": 7, "name": "r", "status": "done",
                                  "working_time_s": 1, "has_unread_result": True, "note_path": None}]
    _reg_on_loop(reg)
    data = json.loads(create_agent_status_handler(reg)())
    assert data["agents"][0]["run_id"] == 7
    assert "result" not in data["agents"][0]    # status omits the result body


def test_list_agents_marshals_through_loop():
    # finding 3: list_agents reads _active/_settled, so it must go through _on_loop.
    from ayder_cli.agents.tool import create_list_agents_handler
    reg = MagicMock()
    reg.list_agents.return_value = [{"name": "r"}]
    calls = []
    reg._on_loop = lambda fn: (calls.append("on_loop"), fn())[1]
    data = json.loads(create_list_agents_handler(reg)())
    assert calls == ["on_loop"]                 # marshalled, not a direct read
    assert data["agents"][0]["name"] == "r"


@pytest.mark.anyio
async def test_read_agent_result_wait_blocks_then_returns():
    from ayder_cli.agents.registry import AgentRegistry
    reg = AgentRegistry(agents={}, parent_config=MagicMock(), project_ctx=MagicMock(),
                        process_manager=MagicMock(), permissions=set())
    reg.set_loop(asyncio.get_running_loop())
    run = AgentRun(3, 0, "x", 0.0, status="working")
    reg._runs[3] = run
    handler = create_read_agent_result_handler(reg)

    async def finish():
        await asyncio.sleep(0.01)
        run.status, run.result = "done", "DONE"
        run.done_event.set()

    asyncio.create_task(finish())
    out = await asyncio.to_thread(handler, run_id=3, wait=True, timeout_s=5)
    assert json.loads(out)["result"] == "DONE"
