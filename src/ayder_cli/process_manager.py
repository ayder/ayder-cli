"""
Background process management for ayder-cli.

Manages long-running processes (dev servers, watchers, builds) in the background.
Imports from core/result.py (NOT from tools/) to avoid circular imports.
"""

import atexit
import os
import re
import signal
import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, Optional

from ayder_cli.core.context import ProjectContext
from ayder_cli.core.result import ToolResult, ToolSuccess, ToolError


def _has_killpg() -> bool:
    """POSIX process-group kill available? (Indirect for test override.)"""
    return hasattr(os, "killpg")


@dataclass
class ManagedProcess:
    """A background process tracked by the ProcessManager."""

    id: int
    command: str
    process: subprocess.Popen
    start_time: float
    status: str = "running"  # "running" or "exited"
    exit_code: Optional[int] = None
    stdout_buffer: Deque[str] = field(default_factory=lambda: deque(maxlen=500))
    stderr_buffer: Deque[str] = field(default_factory=lambda: deque(maxlen=500))
    _stdout_thread: Optional[threading.Thread] = field(default=None, repr=False)
    _stderr_thread: Optional[threading.Thread] = field(default=None, repr=False)


class ProcessManager:
    """Manages background processes with output capture and lifecycle control."""

    def __init__(self, max_processes: int = 5):
        self.max_processes = max_processes
        self._processes: Dict[int, ManagedProcess] = {}
        self._next_id = 1
        self._lock = threading.Lock()
        atexit.register(self._cleanup_all)

    def start_process(self, command: str, cwd: str) -> ManagedProcess:
        """Start a background process with output capture.

        Args:
            command: Shell command to execute.
            cwd: Working directory for the process.

        Returns:
            The ManagedProcess instance.

        Raises:
            RuntimeError: If the max running process limit is reached.
        """
        with self._lock:
            # Refresh statuses before counting
            for mp in self._processes.values():
                if mp.status == "running" and mp.process.poll() is not None:
                    mp.status = "exited"
                    mp.exit_code = mp.process.returncode

            running_count = sum(
                1 for mp in self._processes.values() if mp.status == "running"
            )
            if running_count >= self.max_processes:
                raise RuntimeError(
                    f"Max running processes ({self.max_processes}) reached. "
                    f"Kill a process first."
                )

            proc = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=cwd,
                start_new_session=True,
            )

            mp = ManagedProcess(
                id=self._next_id,
                command=command,
                process=proc,
                start_time=time.time(),
            )

            # Spawn daemon threads to read stdout/stderr into ring buffers
            stdout_thread = threading.Thread(
                target=self._read_stream,
                args=(mp, proc.stdout, mp.stdout_buffer),
                daemon=True,
            )
            stderr_thread = threading.Thread(
                target=self._read_stream,
                args=(mp, proc.stderr, mp.stderr_buffer),
                daemon=True,
            )
            mp._stdout_thread = stdout_thread
            mp._stderr_thread = stderr_thread
            stdout_thread.start()
            stderr_thread.start()

            self._processes[self._next_id] = mp
            self._next_id += 1

        return mp

    def get_process(self, process_id: int) -> Optional[ManagedProcess]:
        """Get a managed process by ID, refreshing its status."""
        mp = self._processes.get(process_id)
        if mp and mp.status == "running":
            ret = mp.process.poll()
            if ret is not None:
                mp.status = "exited"
                mp.exit_code = ret
        return mp

    def kill_process(self, process_id: int) -> bool:
        """Kill a background process and its whole group. SIGTERM, then SIGKILL@5s.

        Returns:
            True if process was killed, False if not found or already exited.
        """
        mp = self.get_process(process_id)
        if mp is None:
            return False
        if mp.status == "exited":
            return False

        self._terminate_tree(mp.process)
        mp.status = "exited"
        mp.exit_code = mp.process.returncode
        return True

    @staticmethod
    def _terminate_tree(proc: subprocess.Popen) -> None:
        """Terminate a process and every child in its group.

        Processes are spawned as session leaders (start_new_session=True), so the
        process-group id equals the child's pid and killpg reaches forked
        grandchildren that would otherwise be orphaned holding a port. Falls back to
        terminate()/kill() where killpg is unavailable (e.g. Windows).
        """
        if _has_killpg():
            try:
                pgid = os.getpgid(proc.pid)
            except (ProcessLookupError, OSError):
                return  # already gone
            try:
                os.killpg(pgid, signal.SIGTERM)
            except (ProcessLookupError, OSError):
                pass
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(pgid, signal.SIGKILL)
                except (ProcessLookupError, OSError):
                    pass
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
        else:
            try:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
            except OSError:
                pass

    def list_processes(self) -> list:
        """Return all managed processes, refreshing statuses."""
        for mp in self._processes.values():
            if mp.status == "running":
                ret = mp.process.poll()
                if ret is not None:
                    mp.status = "exited"
                    mp.exit_code = ret
        return list(self._processes.values())

    def _cleanup_all(self):
        """Terminate all running process groups (called at exit)."""
        for mp in self._processes.values():
            if mp.status == "running":
                try:
                    self._terminate_tree(mp.process)
                except Exception:
                    pass

    @staticmethod
    def _read_stream(mp: ManagedProcess, stream, buffer: Deque[str]):
        """Read lines from a stream into a ring buffer."""
        try:
            for line in stream:
                buffer.append(line.rstrip("\n"))
        except (ValueError, OSError):
            pass  # Stream closed


# ---------------------------------------------------------------------------
# Tool functions (called by registry with DI)
# ---------------------------------------------------------------------------


def run_background_process(
    process_manager: "ProcessManager",
    project_ctx: ProjectContext,
    command: str,
) -> ToolResult:
    """Start a long-running command in the background.

    Args:
        process_manager: The ProcessManager instance (injected).
        project_ctx: Project context for cwd (injected).
        command: Shell command to run.

    Returns:
        ToolSuccess with process ID, or ToolError.
    """
    try:
        mp = process_manager.start_process(command, cwd=str(project_ctx.root))
        return ToolSuccess(
            f"Background process started (ID: {mp.id}, command: {mp.command})"
        )
    except RuntimeError as e:
        return ToolError(str(e), "execution")
    except Exception as e:
        return ToolError(f"Error starting background process: {str(e)}", "execution")


def get_background_output(
    process_manager: "ProcessManager",
    process_id: int,
    tail: int = 50,
) -> ToolResult:
    """Get recent output from a background process.

    Args:
        process_manager: The ProcessManager instance (injected).
        process_id: The process ID.
        tail: Number of recent lines to return (default: 50).

    Returns:
        ToolSuccess with output, or ToolError.
    """
    mp = process_manager.get_process(process_id)
    if mp is None:
        return ToolError(f"No process with ID {process_id}", "validation")

    stdout_lines = list(mp.stdout_buffer)[-tail:]
    stderr_lines = list(mp.stderr_buffer)[-tail:]

    output = f"Process {mp.id} ({mp.status})"
    if mp.exit_code is not None:
        output += f" exit_code={mp.exit_code}"
    output += f"\nCommand: {mp.command}\n"

    if stdout_lines:
        output += f"\n--- STDOUT (last {len(stdout_lines)} lines) ---\n"
        output += "\n".join(stdout_lines) + "\n"
    else:
        output += "\n--- STDOUT ---\n(empty)\n"

    if stderr_lines:
        output += f"\n--- STDERR (last {len(stderr_lines)} lines) ---\n"
        output += "\n".join(stderr_lines) + "\n"

    return ToolSuccess(output)


def kill_background_process(
    process_manager: "ProcessManager",
    process_id: int,
) -> ToolResult:
    """Kill a running background process.

    Args:
        process_manager: The ProcessManager instance (injected).
        process_id: The process ID.

    Returns:
        ToolSuccess or ToolError.
    """
    mp = process_manager.get_process(process_id)
    if mp is None:
        return ToolError(f"No process with ID {process_id}", "validation")

    if mp.status == "exited":
        return ToolError(
            f"Process {process_id} already exited (code={mp.exit_code})", "validation"
        )

    killed = process_manager.kill_process(process_id)
    if killed:
        return ToolSuccess(f"Process {process_id} killed")
    return ToolError(f"Failed to kill process {process_id}", "execution")


def list_background_processes(
    process_manager: "ProcessManager",
) -> ToolResult:
    """List all background processes and their status.

    Args:
        process_manager: The ProcessManager instance (injected).

    Returns:
        ToolSuccess with formatted process list (incl. OS pid).
    """
    processes = process_manager.list_processes()
    if not processes:
        return ToolSuccess("No background processes")

    lines = ["ID  | PID    | Status       | Exit | Command"]
    lines.append("----|--------|--------------|------|--------")
    for mp in processes:
        elapsed = time.time() - mp.start_time
        exit_str = str(mp.exit_code) if mp.exit_code is not None else "-"
        status = mp.status
        if mp.status == "running":
            status = f"running ({elapsed:.0f}s)"
        lines.append(
            f"{mp.id:<3} | {mp.process.pid:<6} | {status:<12} | {exit_str:<4} | {mp.command}"
        )

    return ToolSuccess("\n".join(lines))


# ---------------------------------------------------------------------------
# Best-effort process-tree introspection (no hard dependency; degrades to None)
# ---------------------------------------------------------------------------


def _child_pids(pid: int) -> "list[int] | None":
    """Recursive child pids via ``pgrep -P``. None if pgrep is unavailable.

    Empty list means "no children"; None means "could not determine".
    """
    try:
        found: list[int] = []
        seen: set[int] = set()
        frontier = [pid]
        while frontier:
            current = frontier.pop()
            out = subprocess.run(
                ["pgrep", "-P", str(current)],
                capture_output=True,
                text=True,
                timeout=2,
            )
            for tok in out.stdout.split():
                child = int(tok)
                if child not in seen:
                    seen.add(child)
                    found.append(child)
                    frontier.append(child)
        return sorted(found)
    except FileNotFoundError:
        return None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def _ports_via_lsof(pids: "list[int]") -> "list[int] | None":
    """Listening TCP ports for pids via lsof. None if lsof unavailable."""
    try:
        out = subprocess.run(
            # -a ANDs the selection filters: without it lsof ORs -p with
            # -iTCP and returns every LISTEN socket on the host, not just
            # this pid set's ports.
            ["lsof", "-nP", "-a", "-p", ",".join(str(p) for p in pids),
             "-iTCP", "-sTCP:LISTEN"],
            capture_output=True,
            text=True,
            timeout=3,
        )
    except FileNotFoundError:
        return None
    except (OSError, subprocess.SubprocessError):
        return None
    ports: set[int] = set()
    for line in out.stdout.splitlines():
        m = re.search(r":(\d+)\s+\(LISTEN\)", line)
        if m:
            ports.add(int(m.group(1)))
    return sorted(ports)


def _ports_via_ss(pids: "list[int]") -> "list[int] | None":
    """Listening TCP ports for pids via ss. None if ss unavailable."""
    try:
        out = subprocess.run(
            ["ss", "-tlnp"],
            capture_output=True,
            text=True,
            timeout=3,
        )
    except FileNotFoundError:
        return None
    except (OSError, subprocess.SubprocessError):
        return None
    pidset = {str(p) for p in pids}
    ports: set[int] = set()
    for line in out.stdout.splitlines():
        if "pid=" not in line:
            continue
        if not (set(re.findall(r"pid=(\d+)", line)) & pidset):
            continue
        parts = line.split()
        if len(parts) >= 4:
            port = parts[3].rsplit(":", 1)[-1]
            if port.isdigit():
                ports.add(int(port))
    return sorted(ports)


def _listening_ports(pids: "list[int]") -> "list[int] | None":
    """Best-effort listening ports for a pid set. None if no tool worked."""
    if not pids:
        return []
    if sys.platform == "darwin":
        return _ports_via_lsof(pids)
    ports = _ports_via_ss(pids)
    if ports is None:
        ports = _ports_via_lsof(pids)
    return ports


def _fmt_pids(pids: "list[int] | None") -> str:
    if pids is None:
        return "unknown"
    if not pids:
        return "none"
    return ", ".join(str(p) for p in pids)


def _fmt_ports(ports: "list[int] | None") -> str:
    if ports is None:
        return "unknown"
    if not ports:
        return "none"
    return ", ".join(str(p) for p in ports)


def info_background_process(
    process_manager: "ProcessManager",
    process_id: int,
) -> ToolResult:
    """Deep, best-effort report for one background process.

    Surfaces the OS pid, child pids (pgrep tree), listening ports (lsof/ss),
    status, exit code, full command, and elapsed time. Introspection fields
    degrade to "unknown" rather than failing the call.
    """
    mp = process_manager.get_process(process_id)
    if mp is None:
        return ToolError(f"No process with ID {process_id}", "validation")

    pid = mp.process.pid
    children = _child_pids(pid)
    tree = [pid] + (children or [])
    ports = _listening_ports(tree)
    elapsed = time.time() - mp.start_time

    if mp.exit_code is not None:
        status_line = f"{mp.status} (exit {mp.exit_code})"
    elif mp.status == "running":
        status_line = f"running ({elapsed:.0f}s)"
    else:
        status_line = mp.status

    lines = [
        f"Process {mp.id} (manager id)",
        f"  os pid:   {pid}",
        f"  status:   {status_line}",
        f"  command:  {mp.command}",
        f"  children: {_fmt_pids(children)}",
        f"  ports:    {_fmt_ports(ports)}",
    ]
    return ToolSuccess("\n".join(lines))
