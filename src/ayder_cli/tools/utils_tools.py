"""
Utility tools for ayder-cli.
"""

import logging
import secrets
import shutil
import subprocess
from pathlib import Path

from ayder_cli.core.context import ProjectContext
from ayder_cli.core.result import ToolSuccess, ToolError

logger = logging.getLogger(__name__)


def get_project_structure(project_ctx: ProjectContext, max_depth: int = 3) -> str:
    """Generate a tree-style project structure summary using project root."""
    tree_path = shutil.which("tree")

    if tree_path:
        cmd = [
            tree_path,
            "-L",
            str(max_depth),
            "-I",
            "__pycache__|*.pyc|*.egg-info|.venv|.ayder|.claude|htmlcov|dist|build",
            "--charset",
            "ascii",
            "--noreport",
        ]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=5,
                cwd=str(project_ctx.root),
            )
            if result.returncode == 0:
                return ToolSuccess(result.stdout.strip())
        except Exception:
            pass

    # Fallback to manual tree generation
    return ToolSuccess(_generate_manual_tree(project_ctx, max_depth))


def _generate_manual_tree(project_ctx: ProjectContext, max_depth: int = 3) -> str:
    """Fallback manual tree generator using project root."""
    IGNORE_DIRS = {
        "__pycache__",
        ".venv",
        ".ayder",
        ".claude",
        ".git",
        "htmlcov",
        "dist",
        "build",
        "node_modules",
    }
    IGNORE_PATTERNS = {".pyc", ".egg-info"}

    def should_ignore(name):
        return name in IGNORE_DIRS or any(name.endswith(p) for p in IGNORE_PATTERNS)

    lines = [project_ctx.root.name or "."]

    def walk_dir(path, prefix="", depth=0):
        if depth >= max_depth:
            return
        try:
            entries = sorted(Path(path).iterdir())
        except (PermissionError, FileNotFoundError):
            return

        dirs = [e.name for e in entries if e.is_dir() and not should_ignore(e.name)]
        files = [e.name for e in entries if e.is_file() and not should_ignore(e.name)]

        for i, d in enumerate(dirs):
            is_last_dir = (i == len(dirs) - 1) and len(files) == 0
            connector = "`-- " if is_last_dir else "|-- "
            lines.append(f"{prefix}{connector}{d}/")
            new_prefix = prefix + ("    " if is_last_dir else "|   ")
            walk_dir(Path(path) / d, new_prefix, depth + 1)

        for i, f in enumerate(files):
            is_last = i == len(files) - 1
            connector = "`-- " if is_last else "|-- "
            lines.append(f"{prefix}{connector}{f}")

    walk_dir(project_ctx.root)
    return "\n".join(lines)


def manage_environment_vars(
    project_ctx: ProjectContext, mode: str, variable_name: str | None = None, value: str | None = None
) -> str:
    """
    Manage .env files with four modes:
    - validate: Check if variable_name exists in .env
    - load: Return all variables from .env
    - generate: Generate secure random value for variable_name (16 bytes hex)
    - set: Set variable_name to value in .env

    All write operations (generate/set) require user confirmation via diff preview.
    """
    try:
        # Import python-dotenv here to handle missing dependency gracefully
        try:
            from dotenv import dotenv_values, set_key
        except ImportError:
            return ToolError(
                "Error: python-dotenv library not installed. Run: pip install python-dotenv",
                "validation",
            )

        # Validate mode parameter
        valid_modes = ["validate", "load", "generate", "set"]
        if mode not in valid_modes:
            return ToolError(
                f"Error: Invalid mode '{mode}'. Must be one of: {', '.join(valid_modes)}",
                "validation",
            )

        # Get .env file path (always at project root)
        env_path = project_ctx.validate_path(".env")

        # Mode-specific validation
        if mode in ["validate", "generate", "set"]:
            if not variable_name or not variable_name.strip():
                return ToolError(
                    f"Error: variable_name is required for mode '{mode}'", "validation"
                )

        if mode == "set":
            if value is None:
                return ToolError(
                    "Error: value is required for mode 'set'", "validation"
                )

        # VALIDATE MODE: Check if variable exists
        if mode == "validate":
            if not env_path.exists():
                return ToolError(
                    f"Error: .env file not found at {project_ctx.to_relative(env_path)}",
                    "validation",
                )

            env_vars = dotenv_values(str(env_path))

            if variable_name in env_vars:
                value = env_vars[variable_name]
                # Handle None value (empty variable like FOO=)
                if value is None:
                    return ToolSuccess(
                        f"✓ Variable '{variable_name}' exists in .env\n"
                        f"Value: (empty)"
                    )
                # Mask sensitive values (don't show full secrets)
                if len(value) > 10:
                    masked_value = f"{value[:4]}...{value[-4:]}"
                else:
                    masked_value = "***"

                return ToolSuccess(
                    f"✓ Variable '{variable_name}' exists in .env\n"
                    f"Value: {masked_value}"
                )
            else:
                available_vars = list(env_vars.keys())
                suggestion = ""
                if available_vars:
                    suggestion = (
                        f"\nAvailable variables: {', '.join(available_vars[:10])}"
                    )
                    if len(available_vars) > 10:
                        suggestion += f" (and {len(available_vars) - 10} more)"

                return ToolError(
                    f"✗ Variable '{variable_name}' not found in .env{suggestion}",
                    "validation",
                )

        # LOAD MODE: Display all environment variables
        elif mode == "load":
            if not env_path.exists():
                return ToolSuccess(
                    f"No .env file found at {project_ctx.to_relative(env_path)}\n"
                    "Use 'generate' or 'set' mode to create variables."
                )

            env_vars = dotenv_values(str(env_path))

            if not env_vars:
                return ToolSuccess(".env file is empty")

            # Format output
            output_lines = [
                "=== ENVIRONMENT VARIABLES ===",
                f"File: {project_ctx.to_relative(env_path)}",
                f"Total variables: {len(env_vars)}",
                "",
            ]

            for key, val in env_vars.items():
                # Mask long values for security
                if val and len(val) > 20:
                    masked = f"{val[:8]}...{val[-8:]}"
                else:
                    masked = val or "(empty)"
                output_lines.append(f"{key}={masked}")

            output_lines.append("\n=== END ENVIRONMENT VARIABLES ===")
            return ToolSuccess("\n".join(output_lines))

        # GENERATE MODE: Create secure random value
        elif mode == "generate":
            # variable_name is validated to be non-None above, but mypy needs help
            assert variable_name is not None

            # Generate 16-byte (128-bit) secure random hex value
            generated_value = secrets.token_hex(16)

            # Check if file exists and if variable already exists
            file_exists = env_path.exists()
            variable_existed = False

            if file_exists:
                old_env_vars = dotenv_values(str(env_path))
                variable_existed = variable_name in old_env_vars

            # Create .env if it doesn't exist
            if not file_exists:
                env_path.touch()

            # Set the key using python-dotenv (handles updates and creates if needed)
            success = set_key(
                str(env_path), variable_name, generated_value, quote_mode="never"
            )

            if not success:
                # Rollback if failed
                if not file_exists:
                    env_path.unlink()
                return ToolError(
                    f"Error: Failed to set variable '{variable_name}' in .env",
                    "execution",
                )

            # Success message
            masked_value = f"{generated_value[:8]}...{generated_value[-8:]}"
            action = "updated" if variable_existed else "created"

            return ToolSuccess(
                f"✓ Generated secure value for '{variable_name}' ({action})\n"
                f"Value: {masked_value} (32 chars)\n"
                f"File: {project_ctx.to_relative(env_path)}"
            )

        # SET MODE: Set variable to specific value
        elif mode == "set":
            # variable_name and value are validated to be non-None above, but mypy needs help
            assert variable_name is not None and value is not None

            # Check if file exists and if variable already exists
            file_exists = env_path.exists()
            variable_existed = False

            if file_exists:
                old_env_vars = dotenv_values(str(env_path))
                variable_existed = variable_name in old_env_vars

            # Create .env if it doesn't exist
            if not file_exists:
                env_path.touch()

            # Set the key using python-dotenv
            success = set_key(str(env_path), variable_name, value, quote_mode="never")

            if not success:
                # Rollback if failed
                if not file_exists:
                    env_path.unlink()
                return ToolError(
                    f"Error: Failed to set variable '{variable_name}' in .env",
                    "execution",
                )

            # Success message
            action = "updated" if variable_existed else "created"

            # Mask long values in success message
            if value and len(value) > 20:
                masked_value = f"{value[:8]}...{value[-8:]}"
            else:
                masked_value = value or "(empty)"

            return ToolSuccess(
                f"✓ Variable '{variable_name}' {action}\n"
                f"Value: {masked_value}\n"
                f"File: {project_ctx.to_relative(env_path)}"
            )

    except ValueError as e:
        return ToolError(f"Security Error: {str(e)}", "security")
    except Exception as e:
        return ToolError(f"Error managing environment variables: {str(e)}", "execution")

    # Fallback return to satisfy type checker
    return ToolError("Error: Unknown mode or unexpected error", "validation")
