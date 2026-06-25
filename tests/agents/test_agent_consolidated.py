"""Tests for the consolidated agent(action=...) tool dispatcher."""

import asyncio
import json
from unittest.mock import MagicMock

import pytest

from ayder_cli.agents.tool import AGENT_TOOL_DEFINITION, create_agent_handler
from ayder_cli.tools.definition import ToolDefinition


def _reg():
    reg = MagicMock()
    reg._on_loop.side_effect = lambda fn: fn()
    return reg


class TestDefinition:
    def test_single_tool_named_agent(self):
        assert isinstance(AGENT_TOOL_DEFINITION, ToolDefinition)
        assert AGENT_TOOL_DEFINITION.name == "agent"

    def test_action_enum_and_required(self):
        props = AGENT_TOOL_DEFINITION.parameters["properties"]
        assert set(props["action"]["enum"]) == {"call", "list", "status", "read_result"}
        assert AGENT_TOOL_DEFINITION.parameters["required"] == ["action"]
        for p in ("name", "task", "task_id", "branch_name", "run_id", "wait", "timeout_s"):
            assert p in props

    def test_exposure_and_budget(self):
        assert AGENT_TOOL_DEFINITION.permission == "r"
        assert "core" in AGENT_TOOL_DEFINITION.tags and "agents" in AGENT_TOOL_DEFINITION.tags
        assert AGENT_TOOL_DEFINITION.max_result_chars == 0


class TestDispatch:
    def test_list_returns_agents_json(self):
        reg = _reg()
        reg.list_agents.return_value = [{"name": "reviewer"}]
        assert json.loads(create_agent_handler(reg)(action="list")) == {
            "agents": [{"name": "reviewer"}]
        }

    def test_status_returns_snapshot_json(self):
        reg = _reg()
        reg.snapshot.return_value = [{"run_id": 1, "status": "working"}]
        assert json.loads(create_agent_handler(reg)(action="status"))["agents"][0]["run_id"] == 1

    def test_call_leads_with_run_id_no_state_claim(self):
        reg = _reg()
        reg.create_run.return_value = 7
        reg.run_label.return_value = "TASK-003"
        out = create_agent_handler(reg)(action="call", name="coder", task="do it")
        assert "run #7" in out and "read_result" in out and "TASK-003" in out
        assert "(working)" not in out

    def test_call_without_name_errors(self):
        out = create_agent_handler(_reg())(action="call", task="x")
        assert out.lower().startswith("error") and "name" in out

    def test_call_passes_through_error_string(self):
        reg = _reg()
        reg.create_run.return_value = "Error: Agent 'x' not found."
        assert create_agent_handler(reg)(action="call", name="x", task="y") == (
            "Error: Agent 'x' not found."
        )

    def test_read_result_without_run_id_errors(self):
        assert json.loads(create_agent_handler(_reg())(action="read_result"))["error"]

    def test_read_result_no_wait_uses_on_loop(self):
        reg = _reg()
        reg.read_result.return_value = {"run_id": 3, "result": "DONE"}
        assert json.loads(create_agent_handler(reg)(action="read_result", run_id=3))["result"] == "DONE"

    @pytest.mark.asyncio
    async def test_read_result_wait_uses_coroutine_threadsafe(self):
        reg = MagicMock()
        reg._loop = asyncio.get_running_loop()

        async def _await_run(run_id, timeout_s):
            return {"run_id": run_id, "result": "WAITED"}

        reg.await_run = _await_run
        out = await asyncio.to_thread(
            create_agent_handler(reg), action="read_result", run_id=3, wait=True, timeout_s=5
        )
        assert json.loads(out)["result"] == "WAITED"

    def test_unknown_action_errors(self):
        assert json.loads(create_agent_handler(_reg())(action="frobnicate"))["error"]
