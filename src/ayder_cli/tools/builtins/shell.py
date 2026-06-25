"""
Shell command execution tools for ayder-cli.
"""

import os
import shutil
import subprocess

from ayder_cli.core.context import ProjectContext
from ayder_cli.core.result import ToolSuccess, ToolError

_VALID_SHELLS = ("bash", "zsh", "sh", "busybox")


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
    env = None if not environment else {**os.environ, **environment}
    argv_prefix, shell_note = _resolve_shell(shell)
    try:
        if argv_prefix is not None:
            result = subprocess.run(
                argv_prefix + [command],
                capture_output=True,
                text=True,
                timeout=eff_timeout,
                cwd=str(project_ctx.root),
                env=env,
            )
        else:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=eff_timeout,
                cwd=str(project_ctx.root),
                env=env,
            )

        output = ""
        if shell_note:
            output += shell_note + "\n"
        output += f"Exit Code: {result.returncode}\n"
        if result.stdout:
            output += f"STDOUT:\n{result.stdout}\n"
        if result.stderr:
            output += f"STDERR:\n{result.stderr}\n"

        cap = 8192 if max_result_chars is None else int(max_result_chars)
        return ToolSuccess(_bound_output(output, cap))
    except subprocess.TimeoutExpired:
        return ToolError(f"Error: Command timed out after {eff_timeout}s.", "execution")
    except Exception as e:
        return ToolError(f"Error executing command: {str(e)}", "execution")
