"""Tests for the bash tool (spec 07)."""

import shutil
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


class TestShell:
    def test_invalid_shell_rejected(self, ctx):
        result = bash(ctx, "echo hi", shell="fish")
        assert isinstance(result, ToolError)
        assert "fish" in result

    def test_sh_runs(self, ctx):
        result = bash(ctx, "echo from_sh", shell="sh")
        assert isinstance(result, ToolSuccess)
        assert "from_sh" in result
        assert "Exit Code: 0" in result

    def test_default_uses_bash_argv(self, ctx):
        import subprocess as _sp
        with mock.patch(
            "ayder_cli.tools.builtins.shell.subprocess.run"
        ) as m:
            m.return_value = _sp.CompletedProcess("c", 0, stdout="", stderr="")
            bash(ctx, "echo hi")
            argv = m.call_args.args[0]
            assert argv[0].endswith("bash") and argv[1] == "-c" and argv[2] == "echo hi"

    def test_busybox_argv_form(self, ctx):
        import subprocess as _sp

        def fake_which(name):
            return f"/usr/bin/{name}" if name == "busybox" else None

        with mock.patch("ayder_cli.tools.builtins.shell.shutil.which", side_effect=fake_which), \
             mock.patch("ayder_cli.tools.builtins.shell.subprocess.run") as m:
            m.return_value = _sp.CompletedProcess("c", 0, stdout="", stderr="")
            bash(ctx, "echo hi", shell="busybox")
            argv = m.call_args.args[0]
            assert argv == ["/usr/bin/busybox", "sh", "-c", "echo hi"]

    def test_missing_shell_falls_back_with_note(self, ctx):
        import subprocess as _sp

        def fake_which(name):
            return "/bin/bash" if name == "bash" else None  # zsh missing

        with mock.patch("ayder_cli.tools.builtins.shell.shutil.which", side_effect=fake_which), \
             mock.patch("ayder_cli.tools.builtins.shell.subprocess.run") as m:
            m.return_value = _sp.CompletedProcess("c", 0, stdout="hi\n", stderr="")
            result = bash(ctx, "echo hi", shell="zsh")
            assert "[shell 'zsh' not found; ran with 'bash']" in result

    @pytest.mark.skipif(shutil.which("zsh") is None, reason="needs zsh")
    def test_real_zsh(self, ctx):
        result = bash(ctx, "echo from_zsh", shell="zsh")
        assert "from_zsh" in result


class TestBounding:
    def test_under_cap_unchanged(self, ctx):
        result = bash(ctx, "echo hi", max_result_chars=8192)
        assert "hi" in result
        assert "chars omitted" not in result

    def test_over_cap_middle_truncated(self, ctx):
        from ayder_cli.tools.builtins.shell import _bound_output

        text = "HEAD" + ("x" * 5000) + "TAIL"
        out = _bound_output(text, 512)
        assert len(out) <= 512
        assert "chars omitted" in out
        assert out.startswith("HEAD")
        assert out.endswith("TAIL")

    def test_floor_256(self, ctx):
        from ayder_cli.tools.builtins.shell import _bound_output

        out = _bound_output("y" * 10000, 10)  # below floor -> 256
        assert len(out) <= 256
        assert "chars omitted" in out

    def test_default_cap_8192_applied(self, ctx):
        # 50k of output from the command body; default cap bounds it.
        result = bash(ctx, "for i in $(seq 1 6000); do echo yyyyyyyy; done")
        assert len(result) <= 8192 + 64  # cap + marker slack
        assert "chars omitted" in result
        assert result.startswith("Exit Code: 0")


class TestRegistration:
    def test_definition(self):
        from ayder_cli.tools.definition import TOOL_DEFINITIONS_BY_NAME

        td = TOOL_DEFINITIONS_BY_NAME["bash"]
        assert td.func_ref == "ayder_cli.tools.builtins.shell:bash"
        assert td.permission == "x"
        assert td.safe_mode_blocked is True
        assert td.max_result_chars == 0
        assert td.parameters["required"] == ["command"]
        props = td.parameters["properties"]
        assert set(props) == {"command", "shell", "timeout", "environment", "max_result_chars"}
        assert props["shell"]["enum"] == ["bash", "zsh", "sh", "busybox"]


def test_execute_tool_debug_logs(tmp_path, caplog):
    import logging

    from ayder_cli.tools.execution import execute_tool
    from ayder_cli.tools.hooks import HookManager

    ctx = ProjectContext(str(tmp_path))
    with caplog.at_level(logging.DEBUG, logger="ayder_cli.tools.execution"):
        execute_tool("bash", {"command": "echo hi"}, bash, HookManager(), ctx)
    assert any("bash" in r.getMessage() for r in caplog.records)
