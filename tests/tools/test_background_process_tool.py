"""Tests for the consolidated background_process(action=...) tool (spec 06, AC1-AC8)."""

import time

import pytest

from ayder_cli.core.context import ProjectContext
from ayder_cli.core.result import ToolError, ToolSuccess
from ayder_cli.process_manager import ProcessManager
from ayder_cli.tools.builtins.background_process_tool import background_process

BUDGET = 8192


@pytest.fixture
def pm():
    manager = ProcessManager(max_processes=3)
    yield manager
    manager._cleanup_all()


@pytest.fixture
def ctx(tmp_path):
    return ProjectContext(str(tmp_path))


class TestStart:
    def test_start_returns_id(self, pm, ctx):
        result = background_process(ctx, pm, "start", command="echo hi")
        assert isinstance(result, ToolSuccess)
        assert "ID: 1" in result

    def test_start_requires_command(self, pm, ctx):
        assert isinstance(background_process(ctx, pm, "start"), ToolError)


class TestStop:
    def test_stop_running(self, pm, ctx):
        background_process(ctx, pm, "start", command="sleep 60")
        result = background_process(ctx, pm, "stop", process_id=1)
        assert isinstance(result, ToolSuccess)
        assert "killed" in result

    def test_stop_requires_process_id(self, pm, ctx):
        assert isinstance(background_process(ctx, pm, "stop"), ToolError)

    def test_stop_unknown(self, pm, ctx):
        assert isinstance(background_process(ctx, pm, "stop", process_id=999), ToolError)


class TestLogs:
    def test_logs_returns_output(self, pm, ctx):
        background_process(ctx, pm, "start", command="echo output_line")
        time.sleep(0.2)
        result = background_process(ctx, pm, "logs", process_id=1)
        assert isinstance(result, ToolSuccess)
        assert "output_line" in result

    def test_logs_requires_process_id(self, pm, ctx):
        assert isinstance(background_process(ctx, pm, "logs"), ToolError)

    def test_logs_unknown(self, pm, ctx):
        assert isinstance(background_process(ctx, pm, "logs", process_id=999), ToolError)

    def test_logs_bounds_oversized(self, pm, ctx):
        background_process(ctx, pm, "start", command="echo hi")
        mp = pm.get_process(1)
        mp.process.wait(timeout=5)
        for _ in range(500):
            mp.stdout_buffer.append("y" * 100)
        clamped = background_process(ctx, pm, "logs", process_id=1, tail=500, max_chars=999999)
        assert len(clamped) <= BUDGET
        hinted = background_process(ctx, pm, "logs", process_id=1, tail=500)
        assert "more chars (use offset=" in hinted


class TestList:
    def test_list_empty(self, pm, ctx):
        result = background_process(ctx, pm, "list")
        assert isinstance(result, ToolSuccess)
        assert "No background processes" in result

    def test_list_shows_pid(self, pm, ctx):
        background_process(ctx, pm, "start", command="sleep 30")
        result = background_process(ctx, pm, "list")
        assert str(pm.get_process(1).process.pid) in result


class TestInfoAction:
    def test_info_reports_command(self, pm, ctx):
        background_process(ctx, pm, "start", command="sleep 30")
        result = background_process(ctx, pm, "info", process_id=1)
        assert isinstance(result, ToolSuccess)
        assert "sleep 30" in result

    def test_info_requires_process_id(self, pm, ctx):
        assert isinstance(background_process(ctx, pm, "info"), ToolError)


class TestDispatch:
    def test_unknown_action(self, pm, ctx):
        result = background_process(ctx, pm, "frobnicate")
        assert isinstance(result, ToolError)
        assert "start" in result and "info" in result


class TestRegistration:
    def test_definition_discovered_and_exempt(self):
        from ayder_cli.tools.definition import TOOL_DEFINITIONS_BY_NAME

        td = TOOL_DEFINITIONS_BY_NAME["background_process"]
        assert td.func_ref == (
            "ayder_cli.tools.builtins.background_process_tool:background_process"
        )
        assert td.permission == "x"
        assert td.safe_mode_blocked is True
        assert td.max_result_chars == 0
        assert td.parameters["required"] == ["action"]
        assert td.parameters["properties"]["action"]["enum"] == [
            "start", "logs", "stop", "list", "info",
        ]
