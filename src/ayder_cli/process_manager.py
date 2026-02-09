"""
Background process management for ayder-cli.

Manages long-running processes (dev servers, watchers, builds) in the background.
Imports from core/result.py (NOT from tools/) to avoid circular imports.
"""

import atexit
import signal
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, Optional

from ayder_cli.core.context import ProjectContext
from ayder_cli.core.result import ToolSuccess, ToolError


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
        """Kill a background process. SIGTERM first, SIGKILL after 5s.

        Returns:
            True if process was killed, False if not found or already exited.
        """
        mp = self.get_process(process_id)
        if mp is None:
            return False
        if mp.status == "exited":
            return False

        try:
            mp.process.terminate()
            try:
                mp.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                mp.process.kill()
                mp.process.wait(timeout=5)
        except OSError:
            pass

        mp.status = "exited"
        mp.exit_code = mp.process.returncode
        return True

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
        """Terminate all running processes (called at exit)."""
        for mp in self._processes.values():
            if mp.status == "running":
                try:
                    mp.process.terminate()
                    mp.process.wait(timeout=3)
                except Exception:
                    try:
                        mp.process.kill()
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
) -> str:
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
) -> str:
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
) -> str:
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
) -> str:
    """List all background processes and their status.

    Args:
        process_manager: The ProcessManager instance (injected).

    Returns:
        ToolSuccess with formatted process list.
    """
    processes = process_manager.list_processes()
    if not processes:
        return ToolSuccess("No background processes")

    lines = ["ID  | Status  | Exit | Command"]
    lines.append("----|---------|------|--------")
    for mp in processes:
        elapsed = time.time() - mp.start_time
        exit_str = str(mp.exit_code) if mp.exit_code is not None else "-"
        status = mp.status
        if mp.status == "running":
            status = f"running ({elapsed:.0f}s)"
        lines.append(f"{mp.id:<3} | {status:<7} | {exit_str:<4} | {mp.command}")

    return ToolSuccess("\n".join(lines))
