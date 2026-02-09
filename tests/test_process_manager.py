"""Tests for background process management."""

import time
import pytest

from ayder_cli.process_manager import (
    ProcessManager,
    ManagedProcess,
    run_background_process,
    get_background_output,
    kill_background_process,
    list_background_processes,
)
from ayder_cli.core.context import ProjectContext
from ayder_cli.core.result import ToolSuccess, ToolError


@pytest.fixture
def pm():
    """Create a ProcessManager and clean up after test."""
    manager = ProcessManager(max_processes=3)
    yield manager
    manager._cleanup_all()


@pytest.fixture
def project_ctx(tmp_path):
    return ProjectContext(str(tmp_path))


class TestProcessManager:
    """Test the ProcessManager class directly."""

    def test_start_process(self, pm):
        mp = pm.start_process("echo hello", cwd="/tmp")
        assert mp.id == 1
        assert mp.command == "echo hello"
        assert isinstance(mp, ManagedProcess)

    def test_id_auto_increment(self, pm):
        mp1 = pm.start_process("echo 1", cwd="/tmp")
        mp2 = pm.start_process("echo 2", cwd="/tmp")
        assert mp1.id == 1
        assert mp2.id == 2

    def test_max_limit_enforced(self, pm):
        """Running processes at max limit should raise RuntimeError."""
        # Start 3 long-running processes (max_processes=3)
        for i in range(3):
            pm.start_process("sleep 30", cwd="/tmp")

        with pytest.raises(RuntimeError, match="Max running processes"):
            pm.start_process("sleep 30", cwd="/tmp")

    def test_exited_processes_dont_count_toward_limit(self, pm):
        """Exited processes should not count against the running limit."""
        # Start a fast process that exits immediately
        mp = pm.start_process("echo done", cwd="/tmp")
        mp.process.wait(timeout=5)

        # Now start max_processes long-running ones — should work since echo exited
        for i in range(3):
            pm.start_process("sleep 30", cwd="/tmp")

    def test_get_process(self, pm):
        mp = pm.start_process("echo hello", cwd="/tmp")
        retrieved = pm.get_process(mp.id)
        assert retrieved is not None
        assert retrieved.id == mp.id

    def test_get_process_nonexistent(self, pm):
        assert pm.get_process(999) is None

    def test_get_process_refreshes_status(self, pm):
        mp = pm.start_process("echo quick", cwd="/tmp")
        mp.process.wait(timeout=5)
        retrieved = pm.get_process(mp.id)
        assert retrieved.status == "exited"
        assert retrieved.exit_code == 0

    def test_kill_process(self, pm):
        mp = pm.start_process("sleep 60", cwd="/tmp")
        assert mp.status == "running"
        result = pm.kill_process(mp.id)
        assert result is True
        assert mp.status == "exited"

    def test_kill_nonexistent(self, pm):
        assert pm.kill_process(999) is False

    def test_kill_already_exited(self, pm):
        mp = pm.start_process("echo done", cwd="/tmp")
        mp.process.wait(timeout=5)
        # Refresh status
        pm.get_process(mp.id)
        assert pm.kill_process(mp.id) is False

    def test_list_processes_empty(self, pm):
        assert pm.list_processes() == []

    def test_list_processes_with_entries(self, pm):
        pm.start_process("echo 1", cwd="/tmp")
        pm.start_process("echo 2", cwd="/tmp")
        procs = pm.list_processes()
        assert len(procs) == 2

    def test_stdout_capture(self, pm):
        mp = pm.start_process("echo hello_world", cwd="/tmp")
        mp.process.wait(timeout=5)
        # Give reader thread time to flush
        time.sleep(0.1)
        assert any("hello_world" in line for line in mp.stdout_buffer)

    def test_stderr_capture(self, pm):
        mp = pm.start_process("echo err_msg >&2", cwd="/tmp")
        mp.process.wait(timeout=5)
        time.sleep(0.1)
        assert any("err_msg" in line for line in mp.stderr_buffer)

    def test_cleanup_all(self, pm):
        mp = pm.start_process("sleep 60", cwd="/tmp")
        assert mp.process.poll() is None  # still running
        pm._cleanup_all()
        # Process should be terminated
        mp.process.wait(timeout=5)
        assert mp.process.returncode is not None


class TestRunBackgroundProcess:
    """Test the run_background_process tool function."""

    def test_basic_start(self, pm, project_ctx):
        result = run_background_process(pm, project_ctx, "echo test")
        assert isinstance(result, ToolSuccess)
        assert "ID: 1" in result

    def test_max_limit_error(self, pm, project_ctx):
        for _ in range(3):
            pm.start_process("sleep 30", cwd=str(project_ctx.root))
        result = run_background_process(pm, project_ctx, "sleep 30")
        assert isinstance(result, ToolError)
        assert "Max running processes" in result


class TestGetBackgroundOutput:
    """Test the get_background_output tool function."""

    def test_get_output(self, pm):
        mp = pm.start_process("echo output_line", cwd="/tmp")
        mp.process.wait(timeout=5)
        time.sleep(0.1)
        result = get_background_output(pm, mp.id)
        assert isinstance(result, ToolSuccess)
        assert "output_line" in result

    def test_nonexistent_process(self, pm):
        result = get_background_output(pm, 999)
        assert isinstance(result, ToolError)
        assert "No process with ID 999" in result

    def test_tail_parameter(self, pm):
        # Generate multiple lines
        mp = pm.start_process("for i in $(seq 1 10); do echo line_$i; done", cwd="/tmp")
        mp.process.wait(timeout=5)
        time.sleep(0.1)
        result = get_background_output(pm, mp.id, tail=3)
        assert isinstance(result, ToolSuccess)
        assert "last 3 lines" in result

    def test_exited_process_shows_exit_code(self, pm):
        mp = pm.start_process("exit 42", cwd="/tmp")
        mp.process.wait(timeout=5)
        time.sleep(0.1)
        result = get_background_output(pm, mp.id)
        assert isinstance(result, ToolSuccess)
        assert "exit_code=42" in result


class TestKillBackgroundProcess:
    """Test the kill_background_process tool function."""

    def test_kill_running(self, pm):
        mp = pm.start_process("sleep 60", cwd="/tmp")
        result = kill_background_process(pm, mp.id)
        assert isinstance(result, ToolSuccess)
        assert "killed" in result

    def test_kill_nonexistent(self, pm):
        result = kill_background_process(pm, 999)
        assert isinstance(result, ToolError)
        assert "No process with ID 999" in result

    def test_kill_already_exited(self, pm):
        mp = pm.start_process("echo done", cwd="/tmp")
        mp.process.wait(timeout=5)
        # Refresh status
        pm.get_process(mp.id)
        result = kill_background_process(pm, mp.id)
        assert isinstance(result, ToolError)
        assert "already exited" in result


class TestListBackgroundProcesses:
    """Test the list_background_processes tool function."""

    def test_empty_list(self, pm):
        result = list_background_processes(pm)
        assert isinstance(result, ToolSuccess)
        assert "No background processes" in result

    def test_with_processes(self, pm):
        pm.start_process("sleep 30", cwd="/tmp")
        pm.start_process("echo done", cwd="/tmp")
        result = list_background_processes(pm)
        assert isinstance(result, ToolSuccess)
        assert "sleep 30" in result
        assert "echo done" in result
        assert "ID" in result


class TestConfigMaxBackgroundProcesses:
    """Test config validation for max_background_processes."""

    def test_default_value(self):
        from ayder_cli.core.config import Config
        cfg = Config()
        assert cfg.max_background_processes == 5

    def test_valid_value(self):
        from ayder_cli.core.config import Config
        cfg = Config(max_background_processes=10)
        assert cfg.max_background_processes == 10

    def test_too_low(self):
        from ayder_cli.core.config import Config
        with pytest.raises(Exception):
            Config(max_background_processes=0)

    def test_too_high(self):
        from ayder_cli.core.config import Config
        with pytest.raises(Exception):
            Config(max_background_processes=21)

    def test_boundary_values(self):
        from ayder_cli.core.config import Config
        cfg_min = Config(max_background_processes=1)
        assert cfg_min.max_background_processes == 1
        cfg_max = Config(max_background_processes=20)
        assert cfg_max.max_background_processes == 20
