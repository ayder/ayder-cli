"""Tests for the bash tool (spec 07)."""

import subprocess
from unittest import mock

import pytest

from ayder_cli.core.context import ProjectContext
from ayder_cli.core.result import ToolError, ToolSuccess
from ayder_cli.tools.builtins.shell import bash


@pytest.fixture
def ctx(tmp_path):
    return ProjectContext(str(tmp_path))


class TestTimeout:
    def test_default_timeout_is_120(self, ctx):
        with mock.patch(
            "ayder_cli.tools.builtins.shell.subprocess.run"
        ) as m:
            m.return_value = subprocess.CompletedProcess("c", 0, stdout="", stderr="")
            bash(ctx, "echo hi")
            assert m.call_args.kwargs["timeout"] == 120

    def test_timeout_clamped_to_600(self, ctx):
        with mock.patch(
            "ayder_cli.tools.builtins.shell.subprocess.run"
        ) as m:
            m.return_value = subprocess.CompletedProcess("c", 0, stdout="", stderr="")
            bash(ctx, "echo hi", timeout=99999)
            assert m.call_args.kwargs["timeout"] == 600

    def test_timeout_floor_is_1(self, ctx):
        with mock.patch(
            "ayder_cli.tools.builtins.shell.subprocess.run"
        ) as m:
            m.return_value = subprocess.CompletedProcess("c", 0, stdout="", stderr="")
            bash(ctx, "echo hi", timeout=0)
            assert m.call_args.kwargs["timeout"] == 1

    def test_timeout_expiry_message(self, ctx):
        with mock.patch(
            "ayder_cli.tools.builtins.shell.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="sleep", timeout=1),
        ):
            result = bash(ctx, "sleep 100", timeout=1)
            assert isinstance(result, ToolError)
            assert "timed out" in result.lower()


class TestEnvironment:
    def test_environment_overlay_visible(self, ctx):
        result = bash(ctx, "printenv BASH_TOOL_MARKER", environment={"BASH_TOOL_MARKER": "xyz"})
        assert isinstance(result, ToolSuccess)
        assert "xyz" in result

    def test_environment_overlay_preserves_inherited(self, ctx):
        # PATH is inherited; overlay must not wipe it.
        result = bash(ctx, "printenv PATH", environment={"BASH_TOOL_MARKER": "xyz"})
        assert isinstance(result, ToolSuccess)
        assert "/" in result  # a real PATH came through

    def test_environment_none_passes_env_none(self, ctx):
        with mock.patch(
            "ayder_cli.tools.builtins.shell.subprocess.run"
        ) as m:
            m.return_value = subprocess.CompletedProcess("c", 0, stdout="", stderr="")
            bash(ctx, "echo hi")
            assert m.call_args.kwargs["env"] is None
