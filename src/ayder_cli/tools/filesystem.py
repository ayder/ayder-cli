"""
Filesystem tools for ayder-cli.
"""

import json
import logging
import os

from ayder_cli.core.context import ProjectContext
from ayder_cli.core.result import ToolSuccess, ToolError

logger = logging.getLogger(__name__)

# Maximum file size allowed for read_file() to prevent DoS/memory exhaustion
# Default: 10MB
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 megabytes


def list_files(project_ctx: ProjectContext, directory: str = ".") -> str:
    """Lists files in the specified directory."""
    try:
        abs_dir = project_ctx.validate_path(directory)

        # Ensure it's a directory
        if not abs_dir.is_dir():
            rel_path = project_ctx.to_relative(abs_dir)
            return ToolError(f"Error: '{rel_path}' is not a directory.")

        files = [item.name for item in abs_dir.iterdir()]
        return ToolSuccess(json.dumps(files))

    except ValueError as e:
        return ToolError(f"Security Error: {str(e)}", "security")
    except Exception as e:
        return ToolError(f"Error listing files: {str(e)}", "execution")


def read_file(
    project_ctx: ProjectContext,
    file_path: str,
    start_line: int | None = None,
    end_line: int | None = None,
) -> str:
    """
    Reads the content of a file.
    Can optionally read a specific range of lines (1-based indices).
    """
    try:
        abs_path = project_ctx.validate_path(file_path)

        if not abs_path.exists():
            rel_path = project_ctx.to_relative(abs_path)
            return ToolError(f"Error: File '{rel_path}' does not exist.")

        # Check file size before reading to prevent DoS/memory exhaustion
        file_size = os.path.getsize(abs_path)
        if file_size > MAX_FILE_SIZE:
            rel_path = project_ctx.to_relative(abs_path)
            return ToolError(
                f"Error: File '{rel_path}' is too large ({file_size / (1024 * 1024):.1f}MB). Maximum allowed size is {MAX_FILE_SIZE / (1024 * 1024):.0f}MB."
            )

        with open(abs_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        # Handle line filtering
        if start_line is not None or end_line is not None:
            # Default to beginning/end if one is missing
            start = int(start_line) if start_line else 1
            end = int(end_line) if end_line else len(lines)

            # Adjust to 0-based index
            start_idx = max(0, start - 1)
            end_idx = min(len(lines), end)

            selected_lines = lines[start_idx:end_idx]

            # Add line numbers for context
            content_with_lines = ""
            for i, line in enumerate(selected_lines):
                content_with_lines += f"{start + i}: {line}"

            return ToolSuccess(content_with_lines)
        else:
            return ToolSuccess("".join(lines))

    except ValueError as e:
        return ToolError(f"Security Error: {str(e)}", "security")
    except Exception as e:
        return ToolError(f"Error reading file: {str(e)}", "execution")


def write_file(project_ctx: ProjectContext, file_path: str, content: str) -> str:
    """Writes content to a file (overwrites entire file)."""
    try:
        abs_path = project_ctx.validate_path(file_path)

        # Create parent directories if they don't exist
        abs_path.parent.mkdir(parents=True, exist_ok=True)

        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(content)

        rel_path = project_ctx.to_relative(abs_path)
        return ToolSuccess(f"Successfully wrote to {rel_path}")

    except ValueError as e:
        return ToolError(f"Security Error: {str(e)}", "security")
    except Exception as e:
        return ToolError(f"Error writing file: {str(e)}", "execution")


def replace_string(
    project_ctx: ProjectContext, file_path: str, old_string: str, new_string: str
) -> str:
    """Replaces a specific string in a file with a new string."""
    try:
        abs_path = project_ctx.validate_path(file_path)

        with open(abs_path, "r", encoding="utf-8") as f:
            content = f.read()

        if old_string not in content:
            rel_path = project_ctx.to_relative(abs_path)
            return ToolError(
                f"Error: 'old_string' not found in {rel_path}. No changes made."
            )

        new_content = content.replace(old_string, new_string)

        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(new_content)

        rel_path = project_ctx.to_relative(abs_path)
        return ToolSuccess(f"Successfully replaced text in {rel_path}")

    except ValueError as e:
        return ToolError(f"Security Error: {str(e)}", "security")
    except Exception as e:
        return ToolError(f"Error replacing text: {str(e)}", "execution")


def insert_line(
    project_ctx: ProjectContext, file_path: str, line_number: int, content: str
) -> str:
    """Insert content at a specific line number in a file."""
    try:
        abs_path = project_ctx.validate_path(file_path)

        if not abs_path.exists():
            rel_path = project_ctx.to_relative(abs_path)
            return ToolError(f"Error: File '{rel_path}' does not exist.")

        with open(abs_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        if line_number < 1:
            return ToolError("Error: line_number must be >= 1.", "validation")

        # Clamp to append if beyond end
        idx = min(line_number - 1, len(lines))

        # Ensure content ends with newline
        if content and not content.endswith("\n"):
            content += "\n"

        lines.insert(idx, content)

        with open(abs_path, "w", encoding="utf-8") as f:
            f.writelines(lines)

        rel_path = project_ctx.to_relative(abs_path)
        return ToolSuccess(
            f"Successfully inserted content at line {line_number} in {rel_path}"
        )

    except ValueError as e:
        return ToolError(f"Security Error: {str(e)}", "security")
    except Exception as e:
        return ToolError(f"Error inserting line: {str(e)}", "execution")


def delete_line(project_ctx: ProjectContext, file_path: str, line_number: int) -> str:
    """Delete a specific line from a file."""
    try:
        abs_path = project_ctx.validate_path(file_path)

        if not abs_path.exists():
            rel_path = project_ctx.to_relative(abs_path)
            return ToolError(f"Error: File '{rel_path}' does not exist.")

        with open(abs_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        if line_number < 1 or line_number > len(lines):
            return ToolError(
                f"Error: line_number {line_number} is out of range (1-{len(lines)}).",
                "validation",
            )

        deleted = lines.pop(line_number - 1)

        with open(abs_path, "w", encoding="utf-8") as f:
            f.writelines(lines)

        rel_path = project_ctx.to_relative(abs_path)
        preview = deleted.rstrip("\n")[:80]
        return ToolSuccess(f"Deleted line {line_number} from {rel_path}: '{preview}'")

    except ValueError as e:
        return ToolError(f"Security Error: {str(e)}", "security")
    except Exception as e:
        return ToolError(f"Error deleting line: {str(e)}", "execution")


def get_file_info(project_ctx: ProjectContext, file_path: str) -> str:
    """Get metadata about a file (size, line count, type)."""
    try:
        abs_path = project_ctx.validate_path(file_path)

        if not abs_path.exists():
            rel_path = project_ctx.to_relative(abs_path)
            return ToolError(f"Error: '{rel_path}' does not exist.")

        rel_path = project_ctx.to_relative(abs_path)
        stat = abs_path.stat()
        size_bytes = stat.st_size

        # Human-readable size
        if size_bytes < 1024:
            size_human = f"{size_bytes}B"
        elif size_bytes < 1024 * 1024:
            size_human = f"{size_bytes / 1024:.1f}KB"
        else:
            size_human = f"{size_bytes / (1024 * 1024):.1f}MB"

        # Line count (only for files)
        line_count = None
        if abs_path.is_file():
            try:
                with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                    line_count = sum(1 for _ in f)
            except Exception:
                line_count = None

        info = {
            "path": str(rel_path),
            "size_bytes": size_bytes,
            "size_human": size_human,
            "line_count": line_count,
            "extension": abs_path.suffix or None,
            "is_file": abs_path.is_file(),
            "is_directory": abs_path.is_dir(),
            "is_symlink": abs_path.is_symlink(),
        }

        return ToolSuccess(json.dumps(info, indent=2))

    except ValueError as e:
        return ToolError(f"Security Error: {str(e)}", "security")
    except Exception as e:
        return ToolError(f"Error getting file info: {str(e)}", "execution")
