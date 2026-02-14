"""
Shell command execution tools for ayder-cli.
"""

import subprocess

from ayder_cli.core.context import ProjectContext
from ayder_cli.core.result import ToolSuccess, ToolError


def run_shell_command(project_ctx: ProjectContext, command: str) -> str:
    """Executes a shell command and returns the output.
    Executes with cwd=project.root to sandbox execution to the project."""
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(project_ctx.root),
        )

        output = f"Exit Code: {result.returncode}\n"
        if result.stdout:
            output += f"STDOUT:\n{result.stdout}\n"
        if result.stderr:
            output += f"STDERR:\n{result.stderr}\n"

        return ToolSuccess(output)
    except subprocess.TimeoutExpired:
        return ToolError("Error: Command timed out.", "execution")
    except Exception as e:
        return ToolError(f"Error executing command: {str(e)}", "execution")
