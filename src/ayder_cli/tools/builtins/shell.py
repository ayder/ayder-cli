"""
Shell command execution tools for ayder-cli.
"""

import os
import shutil
import subprocess

from ayder_cli.core.context import ProjectContext
from ayder_cli.core.result import ToolSuccess, ToolError
from ayder_cli.log import get_logger
from ayder_cli.process_manager import ProcessManager

logger = get_logger("tool")

_VALID_SHELLS = ("bash", "zsh", "sh", "busybox")

# Keep git and other tools usable; stop prompts and pagers from waiting for
# input that can never arrive. The caller's `environment` overrides these.
_NONINTERACTIVE_ENV = {
    "GIT_TERMINAL_PROMPT": "0",
    "PAGER": "cat",
    "GIT_PAGER": "cat",
    "DEBIAN_FRONTEND": "noninteractive",
}


def _resolve_shell(shell: str) -> tuple[list[str] | None, str | None]:
    """Return (argv_prefix, note). argv_prefix runs a command string as
    ``argv_prefix + [command]``; None means fall back to ``shell=True`` (/bin/sh).
    note is a one-line fallback notice or None."""
    def prefix_for(name: str) -> list[str] | None:
        path = shutil.which(name)
        if not path:
            return None
        return [path, "sh", "-c"] if name == "busybox" else [path, "-c"]

    prefix = prefix_for(shell)
    if prefix is not None:
        return prefix, None
    for fb in ("bash", "sh"):
        if fb == shell:
            continue
        prefix = prefix_for(fb)
        if prefix is not None:
            return prefix, f"[shell '{shell}' not found; ran with '{fb}']"
    return None, f"[shell '{shell}' not found; ran with '/bin/sh']"


_TRUNCATION_MARKER = "\n… [{} chars omitted] …\n"


def _bound_output(text: str, cap: int) -> str:
    """Middle-truncate to <= max(256, cap) chars, keeping head + tail."""
    cap = max(256, cap)
    if len(text) <= cap:
        return text
    reserve = len(_TRUNCATION_MARKER.format(len(text)))
    body = max(0, cap - reserve)
    head = body // 2
    tail = body - head
    omitted = len(text) - head - tail
    return text[:head] + _TRUNCATION_MARKER.format(omitted) + (text[-tail:] if tail else "")


def _bound_streams(stdout: str, stderr: str, cap: int, prefer_stderr: bool) -> tuple[str, str]:
    """Split *cap* between the streams: the preferred one gets 2/3, unless the
    other needs less, so a large STDOUT can never push STDERR out."""
    if len(stdout) + len(stderr) <= cap:
        return stdout, stderr
    first, second = (stderr, stdout) if prefer_stderr else (stdout, stderr)
    second_cap = min(len(second), cap // 3)
    first_cap = cap - second_cap
    if len(first) < first_cap:
        first_cap = len(first)
        second_cap = cap - first_cap
    first = _bound_output(first, first_cap) if first else first
    second = _bound_output(second, second_cap) if second else second
    return (second, first) if prefer_stderr else (first, second)


def _format_streams(stdout: str, stderr: str, cap: int, prefer_stderr: bool) -> str:
    stdout, stderr = _bound_streams(stdout or "", stderr or "", cap, prefer_stderr)
    text = ""
    if stdout:
        text += f"STDOUT:\n{stdout}\n"
    if stderr:
        text += f"STDERR:\n{stderr}\n"
    return text


def bash(
    project_ctx: ProjectContext,
    command: str,
    shell: str = "bash",
    timeout: int | None = None,
    environment: dict[str, str] | None = None,
    max_result_chars: int | None = None,
) -> str:
    """Executes a shell command and returns exit code + output.
    Executes with cwd=project.root to sandbox execution to the project."""
    if shell not in _VALID_SHELLS:
        return ToolError(
            f"Invalid shell '{shell}'. Choose one of: {', '.join(_VALID_SHELLS)}",
            "validation",
        )
    eff_timeout = 120 if timeout is None else max(1, min(int(timeout), 600))
    env = {**os.environ, **_NONINTERACTIVE_ENV, **(environment or {})}
    argv_prefix, shell_note = _resolve_shell(shell)
    cap = 8192 if max_result_chars is None else int(max_result_chars)
    note = shell_note + "\n" if shell_note else ""
    try:
        # Own session and closed stdin: the command can neither read the TUI's
        # tty nor outlive a timeout in the TUI's process group.
        proc = subprocess.Popen(
            argv_prefix + [command] if argv_prefix is not None else command,
            shell=argv_prefix is None,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            errors="replace",
            cwd=str(project_ctx.root),
            env=env,
            start_new_session=True,
        )
        try:
            stdout, stderr = proc.communicate(timeout=eff_timeout)
        except subprocess.TimeoutExpired:
            ProcessManager._terminate_tree(proc, grace=2.0)
            try:
                stdout, stderr = proc.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                # A process that left the group still holds the pipes open.
                stdout, stderr = "", "[output unavailable: a detached process kept the pipes open]"
            return ToolError(
                f"Timed out after {eff_timeout}s (process group killed). Partial output:\n"
                + note + _format_streams(stdout, stderr, cap, prefer_stderr=True),
                "execution",
            )

        header = note + f"Exit Code: {proc.returncode}\n"
        body = _format_streams(stdout, stderr, max(0, cap - len(header)), proc.returncode != 0)
        return ToolSuccess(header + body)
    except Exception as e:  # noqa: BLE001 - subprocess boundary: model-supplied commands must fail as a ToolError, never as a crash
        return ToolError(f"Error executing command: {str(e)}", "execution")
