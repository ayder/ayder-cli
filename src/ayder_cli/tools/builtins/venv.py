"""
Virtual environment management tools for ayder-cli.
"""

import platform
import shutil
import subprocess

from ayder_cli.core.context import ProjectContext
from ayder_cli.core.result import ToolSuccess, ToolError


def create_virtualenv(
    project_ctx: ProjectContext, env_name: str = ".venv", python_version: str = "3.12"
) -> str:
    """
    Create a new Python virtual environment.

    Uses Python's built-in venv module to create an isolated environment.
    """
    try:
        # Validate env_name contains no path traversal
        if ".." in env_name or env_name.startswith("/"):
            return ToolError(
                f"Security Error: Invalid virtual environment name '{env_name}'. "
                "Name must not contain '..' or start with '/'.",
                "security",
            )

        # Validate path
        abs_env_path = project_ctx.validate_path(env_name)

        # Check if environment already exists
        if abs_env_path.exists():
            rel_path = project_ctx.to_relative(abs_env_path)
            return ToolError(
                f"Error: Virtual environment already exists at '{rel_path}'. "
                "Please remove it first or use a different name.",
                "validation",
            )

        # Validate Python version (basic check for common versions)
        common_versions = ["3.8", "3.9", "3.10", "3.11", "3.12", "3.13"]
        if python_version not in common_versions:
            return ToolError(
                f"Warning: Python version '{python_version}' may not be available. "
                f"Common versions: {', '.join(common_versions)}.",
                "validation",
            )

        # Find Python executable for the specified version
        python_executable = f"python{python_version}"

        # Try to find the Python executable
        python_path = shutil.which(python_executable)

        if python_path is None:
            # Fallback to default python
            python_path = shutil.which("python")
            if python_path is None:
                # Last resort: use 'python' and hope for the best
                python_path = "python"

        # Create the virtual environment using subprocess
        cmd = [python_path, "-m", "venv", str(abs_env_path)]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

        if result.returncode != 0:
            return ToolError(
                f"Error: Failed to create virtual environment. "
                f"Command: {' '.join(cmd)}\n"
                f"STDERR: {result.stderr}",
                "execution",
            )

        rel_path = project_ctx.to_relative(abs_env_path)
        return ToolSuccess(
            f"✓ Virtual environment created successfully at '{rel_path}'\n"
            f"  Python version: {python_version}\n"
            f"  Use 'activate_virtualenv' to get activation instructions."
        )

    except ValueError as e:
        return ToolError(f"Security Error: {str(e)}", "security")
    except subprocess.TimeoutExpired:
        return ToolError("Error: Virtual environment creation timed out.", "execution")
    except Exception as e:
        return ToolError(f"Error creating virtual environment: {str(e)}", "execution")


def install_requirements(
    project_ctx: ProjectContext,
    requirements_file: str = "requirements.txt",
    env_name: str = ".venv",
) -> str:
    """
    Install project dependencies from requirements.txt or pyproject.toml.

    Uses pip from the virtual environment to install dependencies.
    """
    try:
        # Validate paths
        abs_env_path = project_ctx.validate_path(env_name)
        abs_req_path = project_ctx.validate_path(requirements_file)

        # Check if virtual environment exists
        if not abs_env_path.exists():
            rel_env = project_ctx.to_relative(abs_env_path)
            return ToolError(
                f"Error: Virtual environment not found at '{rel_env}'. "
                "Please create it first using 'create_virtualenv'.",
                "validation",
            )

        # Find pip executable in virtual environment
        if platform.system() == "Windows":
            pip_path = abs_env_path / "Scripts" / "pip.exe"
        else:
            pip_path = abs_env_path / "bin" / "pip"

        if not pip_path.exists() and not pip_path.with_suffix(".exe").exists():
            return ToolError(
                f"Error: pip not found in virtual environment at '{project_ctx.to_relative(abs_env_path)}'. "
                f"Expected path: {project_ctx.to_relative(pip_path)}",
                "execution",
            )

        # Use pip from the virtual environment
        pip_cmd = (
            str(pip_path) if pip_path.exists() else str(pip_path.with_suffix(".exe"))
        )

        # Check if requirements file exists
        if not abs_req_path.exists():
            rel_req = project_ctx.to_relative(abs_req_path)
            return ToolError(
                f"Error: Requirements file not found: '{rel_req}'", "validation"
            )

        # Run pip install
        cmd = [pip_cmd, "install", "-r", str(abs_req_path)]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minutes for installation
        )

        if result.returncode != 0:
            return ToolError(
                f"Error: Failed to install dependencies.\n"
                f"Command: {' '.join(cmd)}\n"
                f"STDERR: {result.stderr}",
                "execution",
            )

        # Parse output for summary
        output_lines = result.stdout.strip().split("\n")
        summary_lines = [
            line
            for line in output_lines
            if "successfully" in line.lower() or "installed" in line.lower()
        ]

        if summary_lines:
            summary = "\n".join(summary_lines[-3:])  # Last 3 lines of summary
        else:
            summary = "Dependencies installed successfully"

        rel_req = project_ctx.to_relative(abs_req_path)
        rel_env = project_ctx.to_relative(abs_env_path)
        return ToolSuccess(
            f"✓ Dependencies installed successfully from '{rel_req}'\n"
            f"  Virtual environment: '{rel_env}'\n"
            f"  Summary:\n{summary}"
        )

    except ValueError as e:
        return ToolError(f"Security Error: {str(e)}", "security")
    except subprocess.TimeoutExpired:
        return ToolError("Error: Installation timed out after 5 minutes.", "execution")
    except Exception as e:
        return ToolError(f"Error installing requirements: {str(e)}", "execution")


def list_virtualenvs(project_ctx: ProjectContext) -> str:
    """
    List all virtual environments in the project directory.

    Scans for directories matching .venv* pattern.
    """
    try:
        # Get the project root
        project_root = project_ctx.root

        # Scan for virtual environment directories
        venv_dirs = []
        for item in project_root.iterdir():
            if item.is_dir() and (
                item.name == ".venv" or item.name.startswith(".venv")
            ):
                venv_dirs.append(item)

        # Sort for consistent output
        venv_dirs.sort(key=lambda x: x.name)

        if not venv_dirs:
            return ToolSuccess(
                "No virtual environments found in the project directory.\n"
                "Use 'create_virtualenv' to create a new virtual environment."
            )

        # Build the output
        output_lines = ["Available Virtual Environments:"]
        output_lines.append("-" * 50)

        for venv_dir in venv_dirs:
            # Get Python version from pyvenv.cfg if available
            pyvenv_cfg = venv_dir / "pyvenv.cfg"
            python_version = "Unknown"

            if pyvenv_cfg.exists():
                try:
                    with open(pyvenv_cfg, "r") as f:
                        for line in f:
                            if line.startswith("version = "):
                                python_version = line.split("=")[1].strip()
                                break
                except Exception:
                    python_version = "Unknown"

            # Check if this might be the active environment
            active_marker = ""

            output_lines.append(
                f"  • {venv_dir.name.ljust(20)} (Python {python_version}){active_marker}"
            )

        output_lines.append("-" * 50)
        output_lines.append(f"Total environments: {len(venv_dirs)}")

        return ToolSuccess("\n".join(output_lines))

    except Exception as e:
        return ToolError(f"Error listing virtual environments: {str(e)}", "execution")


def activate_virtualenv(project_ctx: ProjectContext, env_name: str = ".venv") -> str:
    """
    Get activation instructions for a virtual environment.

    Provides shell-specific commands for different shells.
    """
    try:
        # Validate path
        abs_env_path = project_ctx.validate_path(env_name)

        # Check if environment exists
        if not abs_env_path.exists():
            rel_path = project_ctx.to_relative(abs_env_path)
            return ToolError(
                f"Error: Virtual environment not found at '{rel_path}'.", "validation"
            )

        rel_path = project_ctx.to_relative(abs_env_path)

        # Determine the system and provide appropriate activation commands
        output_lines = [
            f"To activate the virtual environment '{rel_path}', use the appropriate command for your shell:",
            "",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "",
        ]

        # Common activation commands
        if platform.system() == "Windows":
            output_lines.extend(
                [
                    "PowerShell:",
                    f"  {rel_path}\\Scripts\\Activate.ps1",
                    "",
                    "Command Prompt:",
                    f"  {rel_path}\\Scripts\\activate.bat",
                    "",
                ]
            )
        else:
            output_lines.extend(
                [
                    "Bash / Zsh:",
                    f"  source {rel_path}/bin/activate",
                    "",
                    "Fish:",
                    f"  source {rel_path}/bin/activate.fish",
                    "",
                    "TCSH / CSH:",
                    f"  source {rel_path}/bin/activate.csh",
                    "",
                ]
            )

        output_lines.extend(
            [
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                "",
                "To deactivate the virtual environment, run:",
                "  deactivate",
            ]
        )

        return ToolSuccess("\n".join(output_lines))

    except ValueError as e:
        return ToolError(f"Security Error: {str(e)}", "security")
    except Exception as e:
        return ToolError(
            f"Error getting activation instructions: {str(e)}", "execution"
        )


def remove_virtualenv(
    project_ctx: ProjectContext, env_name: str = ".venv", force: bool = False
) -> str:
    """
    Remove/uninstall a virtual environment.
    """
    try:
        # Validate path
        abs_env_path = project_ctx.validate_path(env_name)

        # Check if environment exists
        if not abs_env_path.exists():
            rel_path = project_ctx.to_relative(abs_env_path)
            return ToolError(
                f"Error: Virtual environment not found at '{rel_path}'.", "validation"
            )

        # Check if it's actually a directory (not a file with same name)
        if not abs_env_path.is_dir():
            rel_path = project_ctx.to_relative(abs_env_path)
            return ToolError(f"Error: '{rel_path}' is not a directory.", "validation")

        # Ask for confirmation unless force is True
        if not force:
            rel_path = project_ctx.to_relative(abs_env_path)
            return ToolError(
                f"⚠️  Confirmation Required\n\n"
                f"Are you sure you want to remove the virtual environment at '{rel_path}'?\n"
                f"This action cannot be undone!\n\n"
                f"To confirm, run this command again with `force=True`:\n"
                f"  remove_virtualenv(env_name='{rel_path}', force=True)\n\n"
                f"Current directory contents:\n"
                f"{len(list(abs_env_path.iterdir()))} items will be deleted.",
                "validation",
            )

        shutil.rmtree(abs_env_path)

        rel_path = project_ctx.to_relative(abs_env_path)
        return ToolSuccess(f"✓ Virtual environment removed successfully: '{rel_path}'")

    except ValueError as e:
        return ToolError(f"Security Error: {str(e)}", "security")
    except Exception as e:
        return ToolError(f"Error removing virtual environment: {str(e)}", "execution")
