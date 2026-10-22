"""bash and background processes never hold the TUI's stdin or leak children
(audit P1-1..P1-4).

Real processes, POSIX only. fd 0 is swapped for a pipe that never closes, so a
child that inherits stdin blocks deterministically instead of racing the
terminal. No network (environment: local-faked).
"""

import os
import signal
import time
from contextlib import suppress

import pytest

from ayder_cli.core.context import ProjectContext
from ayder_cli.core.result import ToolError, ToolSuccess
from ayder_cli.process_manager import ProcessManager, kill_background_process
from ayder_cli.tools.builtins.shell import bash

pytestmark = pytest.mark.skipif(not hasattr(os, "killpg"), reason="POSIX process groups")


@pytest.fixture
def ctx(tmp_path):
    return ProjectContext(str(tmp_path))


@pytest.fixture
def blocking_stdin():
    """Make fd 0 a pipe nobody writes to, as the TUI's tty is for a child."""
    r, w = os.pipe()
    saved = os.dup(0)
    os.dup2(r, 0)
    try:
        yield
    finally:
        os.dup2(saved, 0)
        for fd in (saved, r, w):
            os.close(fd)


@pytest.fixture
def pm():
    manager = ProcessManager(max_processes=3)
    yield manager
    manager._cleanup_all()


def _gone(pid, wait=3.0):
    """True once ``pid`` no longer exists (a reparented child is reaped by init)."""
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.05)
    return False


def _reap(pid):
    with suppress(ProcessLookupError, PermissionError):
        os.kill(pid, signal.SIGKILL)


# --- bash (P1-1, P1-2, P1-3) ---


def test_bash_does_not_read_inherited_stdin(ctx, blocking_stdin):
    """Baseline regression (P1-1): `read` waited on the TUI's tty until the timeout."""
    start = time.monotonic()
    out = bash(ctx, "read x; echo got:$x", timeout=5)
    assert time.monotonic() - start < 2
    assert isinstance(out, ToolSuccess) and "Exit Code: 0" in out and "got:" in out


def test_bash_noninteractive_env(ctx):
    """New interface (P1-1): prompts and pagers are off unless the caller overrides."""
    out = bash(ctx, 'echo "$GIT_TERMINAL_PROMPT|$PAGER|$GIT_PAGER|$DEBIAN_FRONTEND"')
    assert "0|cat|cat|noninteractive" in out
    assert "|less|" in bash(ctx, 'echo "|$PAGER|"', environment={"PAGER": "less"})


def test_git_stays_usable(ctx):
    """Preservation: only prompts and pagers are off; normal git works, and log prints without a pager."""
    out = bash(ctx, "git init -q && git -c user.email=a@b -c user.name=n commit --allow-empty -qm probe "
                    "&& git log --oneline && git status --short && echo done")
    assert "Exit Code: 0" in out and "probe" in out and "done" in out


def test_git_prompt_opt_out_per_call(ctx):
    """Preservation: the caller's environment wins, also over the new defaults."""
    out = bash(ctx, 'echo "[$GIT_TERMINAL_PROMPT]"', environment={"GIT_TERMINAL_PROMPT": "1"})
    assert "[1]" in out


def test_bash_timeout_kills_group_and_keeps_output(ctx, tmp_path):
    """Baseline regression (P1-2): output was lost and the child orphaned."""
    out = bash(ctx, "echo before; sleep 30 & echo $! > child.pid; wait", timeout=1)
    child = int((tmp_path / "child.pid").read_text().strip())
    try:
        assert isinstance(out, ToolError) and out.category == "execution"
        assert "process group killed" in out and "before" in out
        assert _gone(child)
    finally:
        _reap(child)


def test_bash_binary_output(ctx):
    """Baseline regression (P1-3): non-UTF-8 output raised a decode error."""
    out = bash(ctx, r"printf '\377\376'")
    assert isinstance(out, ToolSuccess) and "Exit Code: 0" in out


def test_bash_stderr_survives_large_stdout(ctx):
    """Baseline regression (P1-3): middle truncation dropped the start of STDERR."""
    cmd = "python3 -c \"import sys; print('x'*50000); sys.stderr.write('BOOM' + 'y'*5000)\"; exit 1"
    out = bash(ctx, cmd, max_result_chars=2000)
    assert "BOOM" in out and "Exit Code: 1" in out


# --- background_process (P1-1, P1-4) ---


def test_background_does_not_read_inherited_stdin(pm, tmp_path, blocking_stdin):
    """Baseline regression (P1-1): a background `read` waited on the TUI's stdin."""
    mp = pm.start_process("read x; echo got:$x", cwd=str(tmp_path))
    mp.process.wait(timeout=3)
    assert mp.process.returncode == 0


def _leader_exits_child_lives(pm, tmp_path):
    mp = pm.start_process("sleep 30 & echo $! > child.pid; echo leader-exits", cwd=str(tmp_path))
    mp.process.wait(timeout=5)
    return mp, int((tmp_path / "child.pid").read_text().strip())


def test_stop_kills_children_after_leader_exit(pm, tmp_path):
    """Baseline regression (P1-4): 'already exited' left the child running."""
    mp, child = _leader_exits_child_lives(pm, tmp_path)
    try:
        r = kill_background_process(pm, mp.id)
        assert isinstance(r, ToolSuccess) and "leader had exited" in r
        assert _gone(child)
    finally:
        _reap(child)


def test_cleanup_kills_children_after_leader_exit(pm, tmp_path):
    """Baseline regression (P1-4): exit cleanup skipped exited leaders."""
    _, child = _leader_exits_child_lives(pm, tmp_path)
    try:
        pm._cleanup_all()
        assert _gone(child)
    finally:
        _reap(child)


def test_stop_fully_exited_is_success(pm, tmp_path):
    """Baseline regression (P1-4): stopping a finished process was a validation error."""
    mp = pm.start_process("echo done", cwd=str(tmp_path))
    mp.process.wait(timeout=5)
    r = kill_background_process(pm, mp.id)
    assert isinstance(r, ToolSuccess) and "nothing left running" in r


def test_gone_group_is_never_signalled_again(pm, tmp_path, monkeypatch):
    """Baseline regression (review): a reaped leader's pid can be reused by an
    unrelated group; once the group was seen empty it must not be signalled."""
    import ayder_cli.process_manager as pmmod

    mp = pm.start_process("echo done", cwd=str(tmp_path))
    mp.process.wait(timeout=5)
    pm.kill_process(mp.id)  # observes the empty group

    sent = []
    monkeypatch.setattr(pmmod, "_group_alive", lambda pgid: True)  # the pid was reused
    monkeypatch.setattr(pmmod.os, "killpg", lambda pgid, sig: sent.append((pgid, sig)))
    pm.kill_process(mp.id)
    pm._cleanup_all()
    assert sent == []


def test_status_refresh_marks_an_empty_group_gone(pm, tmp_path, monkeypatch):
    """Baseline regression (review): a process that exited on its own and was
    never stopped got its (possibly reused) pgid signalled at exit."""
    import ayder_cli.process_manager as pmmod

    mp = pm.start_process("echo done", cwd=str(tmp_path))
    mp.process.wait(timeout=5)
    pm.list_processes()  # the refresh sees the leader exited and the group empty

    sent = []
    monkeypatch.setattr(pmmod, "_group_alive", lambda pgid: True)
    monkeypatch.setattr(pmmod.os, "killpg", lambda pgid, sig: sent.append((pgid, sig)))
    pm._cleanup_all()
    assert sent == []
