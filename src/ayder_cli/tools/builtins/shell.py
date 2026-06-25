"""
Shell command execution tools for ayder-cli.
"""

import os
import subprocess

from ayder_cli.core.context import ProjectContext
from ayder_cli.core.result import ToolSuccess, ToolError


def bash(
    project_ctx: ProjectContext,
    command: str,
    timeout: int | None = None,
    environment: dict[str, str] | None = None,
) -> str:
    """Executes a shell command and returns exit code + output.
    Executes with cwd=project.root to sandbox execution to the project."""
    eff_timeout = 120 if timeout is None else max(1, min(int(timeout), 600))
    env = None if not environment else {**os.environ, **environment}
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=eff_timeout,
            cwd=str(project_ctx.root),
            env=env,
        )

        output = f"Exit Code: {result.returncode}\n"
        if result.stdout:
            output += f"STDOUT:\n{result.stdout}\n"
        if result.stderr:
            output += f"STDERR:\n{result.stderr}\n"

        return ToolSuccess(output)
    except subprocess.TimeoutExpired:
        return ToolError(f"Error: Command timed out after {eff_timeout}s.", "execution")
    except Exception as e:
        return ToolError(f"Error executing command: {str(e)}", "execution")
