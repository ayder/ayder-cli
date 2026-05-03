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
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

# Default page size for read_file when no explicit range is given. Mirrors
# Claude Code's Read tool — large enough for most source files in one shot,
# small enough that small-context LLMs don't drown.
READ_FILE_DEFAULT_LINES = 2000


def _format_size(n_bytes: int) -> str:
    if n_bytes < 1024:
        return f"{n_bytes}B"
    if n_bytes < 1024 * 1024:
        return f"{n_bytes / 1024:.1f}KB"
    return f"{n_bytes / (1024 * 1024):.1f}MB"


def read_file(
    project_ctx: ProjectContext,
    file_path: str,
    start_line: int | None = None,
    end_line: int | None = None,
) -> str:
    """Read a file with explicit pagination semantics.

    Behavior:
    - With no range: reads up to ``READ_FILE_DEFAULT_LINES`` starting at line 1.
      If the file is longer, the result includes a footer naming the total
      line count and the exact follow-up call needed to read the next page.
    - With ``start_line`` / ``end_line``: reads that explicit slice (1-based,
      inclusive). The same pagination footer is appended if more content
      remains beyond the slice.
    - The returned body always uses ``"<line_no>: <text>"`` formatting so the
      caller can never confuse partial output for a complete file.
    """
    try:
        abs_path = project_ctx.validate_path(file_path)

        if not abs_path.exists():
            rel_path = project_ctx.to_relative(abs_path)
            return ToolError(f"Error: File '{rel_path}' does not exist.")

        file_size = os.path.getsize(abs_path)
        if file_size > MAX_FILE_SIZE:
            rel_path = project_ctx.to_relative(abs_path)
            return ToolError(
                f"Error: File '{rel_path}' is too large "
                f"({file_size / (1024 * 1024):.1f}MB). "
                f"Maximum allowed size is {MAX_FILE_SIZE / (1024 * 1024):.0f}MB."
            )

        with open(abs_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        total_lines = len(lines)
        rel_path = str(project_ctx.to_relative(abs_path))

        explicit_range = start_line is not None or end_line is not None

        if explicit_range:
            start = int(start_line) if start_line else 1
            end = int(end_line) if end_line else total_lines
        else:
            start = 1
            end = min(total_lines, READ_FILE_DEFAULT_LINES)

        start_idx = max(0, start - 1)
        end_idx = min(total_lines, end)
        selected = lines[start_idx:end_idx]

        body = "".join(f"{start + i}: {line}" for i, line in enumerate(selected))

        # Always append a footer so the caller never has to infer completeness
        # from absence. Two shapes:
        #   - more remaining → name the next call to make
        #   - reached EOF    → explicit [COMPLETE] marker
        last_returned = start_idx + len(selected)
        more_remaining = last_returned < total_lines

        if more_remaining:
            footer = (
                f"\n[FILE: {rel_path} | {total_lines} total lines, "
                f"{_format_size(file_size)} | showing lines "
                f"{start_idx + 1}-{last_returned}. "
                f"To read more: read_file(file_path={rel_path!r}, "
                f"start_line={last_returned + 1})]"
            )
        else:
            footer = (
                f"\n[FILE: {rel_path} | COMPLETE: {total_lines} lines, "
                f"{_format_size(file_size)} | showing lines "
                f"{start_idx + 1}-{last_returned}]"
            )
        return ToolSuccess(body + footer)

    except ValueError as e:
        return ToolError(f"Security Error: {str(e)}", "security")
    except Exception as e:
        return ToolError(f"Error reading file: {str(e)}", "execution")


def file_explorer(project_ctx: ProjectContext, path: str = ".") -> str:
    """List files in a directory or get metadata for a specific file."""
    try:
        abs_path = project_ctx.validate_path(path)
        
        if abs_path.is_dir():
            files = [item.name for item in abs_path.iterdir()]
            return ToolSuccess(json.dumps(files))
            
        elif abs_path.exists():
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
        else:
            rel_path = project_ctx.to_relative(abs_path)
            return ToolError(f"Error: '{rel_path}' does not exist.")
            
    except ValueError as e:
        return ToolError(f"Security Error: {str(e)}", "security")
    except Exception as e:
        return ToolError(f"Error exploring path: {str(e)}", "execution")


def file_editor(
    project_ctx: ProjectContext, 
    file_path: str, 
    operation: str,
    content: str | None = None,
    old_string: str | None = None,
    new_string: str | None = None,
    line_number: int | None = None,
) -> str:
    """Modify files with specific operations."""
    try:
        abs_path = project_ctx.validate_path(file_path)
        
        if operation == "write":
            if content is None:
                return ToolError("Error: 'content' parameter is required for 'write' operation.", "validation")
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(content)
            rel_path = project_ctx.to_relative(abs_path)
            return ToolSuccess(f"Successfully wrote to {rel_path}")
            
        elif operation == "replace":
            if old_string is None or new_string is None:
                return ToolError("Error: 'old_string' and 'new_string' are required for 'replace' operation.", "validation")
            if not abs_path.exists():
                rel_path = project_ctx.to_relative(abs_path)
                return ToolError(f"Error: File '{rel_path}' does not exist.")
            with open(abs_path, "r", encoding="utf-8") as f:
                file_content = f.read()
            if old_string not in file_content:
                rel_path = project_ctx.to_relative(abs_path)
                return ToolError(f"Error: 'old_string' not found in {rel_path}. No changes made.")
            new_content = file_content.replace(old_string, new_string)
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(new_content)
            rel_path = project_ctx.to_relative(abs_path)
            return ToolSuccess(f"Successfully replaced text in {rel_path}")
            
        elif operation == "insert":
            if line_number is None or content is None:
                return ToolError("Error: 'line_number' and 'content' are required for 'insert' operation.", "validation")
            if not abs_path.exists():
                rel_path = project_ctx.to_relative(abs_path)
                return ToolError(f"Error: File '{rel_path}' does not exist.")
            with open(abs_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            if line_number < 1:
                return ToolError("Error: line_number must be >= 1.", "validation")
            idx = min(line_number - 1, len(lines))
            if content and not content.endswith("\n"):
                content += "\n"
            lines.insert(idx, content)
            with open(abs_path, "w", encoding="utf-8") as f:
                f.writelines(lines)
            rel_path = project_ctx.to_relative(abs_path)
            return ToolSuccess(f"Successfully inserted content at line {line_number} in {rel_path}")
            
        elif operation == "delete":
            if line_number is None:
                return ToolError("Error: 'line_number' is required for 'delete' operation.", "validation")
            if not abs_path.exists():
                rel_path = project_ctx.to_relative(abs_path)
                return ToolError(f"Error: File '{rel_path}' does not exist.")
            with open(abs_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            if line_number < 1 or line_number > len(lines):
                return ToolError(f"Error: line_number {line_number} is out of range (1-{len(lines)}).", "validation")
            deleted = lines.pop(line_number - 1)
            with open(abs_path, "w", encoding="utf-8") as f:
                f.writelines(lines)
            rel_path = project_ctx.to_relative(abs_path)
            preview = deleted.rstrip("\n")[:80]
            return ToolSuccess(f"Deleted line {line_number} from {rel_path}: '{preview}'")
            
        else:
            return ToolError(f"Error: Unknown operation '{operation}'", "validation")
            
    except ValueError as e:
        return ToolError(f"Security Error: {str(e)}", "security")
    except Exception as e:
        return ToolError(f"Error executing file_editor: {str(e)}", "execution")
