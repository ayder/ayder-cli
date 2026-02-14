"""
Codebase search tools for ayder-cli.
"""

import logging
import shutil
import subprocess
from pathlib import Path

from ayder_cli.core.context import ProjectContext
from ayder_cli.core.result import ToolSuccess, ToolError

logger = logging.getLogger(__name__)


def search_codebase(
    project_ctx: ProjectContext,
    pattern: str,
    file_pattern: str | None = None,
    case_sensitive: bool = True,
    context_lines: int = 0,
    max_results: int = 50,
    directory: str = ".",
    output_format: str = "full",
) -> str:
    """
    Search for a pattern across the codebase using ripgrep (or grep fallback).
    Returns matching lines with file paths and line numbers.
    Supports output_format: 'full' (default), 'files_only', 'count'.
    """
    try:
        abs_dir = project_ctx.validate_path(directory)

        # Ensure it's a directory
        if not abs_dir.is_dir():
            rel_path = project_ctx.to_relative(abs_dir)
            return ToolError(f"Error: '{rel_path}' is not a directory.")

        rg_path = shutil.which("rg")

        if rg_path:
            return _search_with_ripgrep(
                pattern,
                file_pattern,
                case_sensitive,
                context_lines,
                max_results,
                abs_dir,
                project_ctx,
                output_format,
            )
        else:
            return _search_with_grep(
                pattern,
                file_pattern,
                case_sensitive,
                context_lines,
                max_results,
                abs_dir,
                project_ctx,
                output_format,
            )
    except ValueError as e:
        return ToolError(f"Security Error: {str(e)}", "security")
    except Exception as e:
        return ToolError(f"Error during search: {str(e)}", "execution")


def _search_with_ripgrep(
    pattern,
    file_pattern,
    case_sensitive,
    context_lines,
    max_results,
    abs_directory,
    project_ctx,
    output_format="full",
):
    """Implementation using ripgrep."""
    cmd = [shutil.which("rg"), "--color", "never", "--no-messages"]

    if output_format == "files_only":
        cmd.append("--files-with-matches")
    elif output_format == "count":
        cmd.append("--count")
    else:
        cmd.extend(["--line-number", "--heading", "--max-count", str(max_results)])

    if not case_sensitive:
        cmd.append("--ignore-case")
    if context_lines > 0 and output_format == "full":
        cmd.extend(["--context", str(context_lines)])
    if file_pattern:
        cmd.extend(["--glob", file_pattern])

    # Ignore common build artifacts
    for ignore in [
        "!.git/",
        "!__pycache__/",
        "!*.pyc",
        "!.venv/",
        "!.ayder/",
        "!.claude/",
        "!dist/",
        "!build/",
        "!*.egg-info/",
        "!htmlcov/",
    ]:
        cmd.extend(["--glob", ignore])

    cmd.extend([pattern, str(abs_directory)])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            if output_format == "files_only":
                return ToolSuccess(
                    _format_files_only(result.stdout, pattern, project_ctx)
                )
            elif output_format == "count":
                return ToolSuccess(
                    _format_count_results(result.stdout, pattern, project_ctx)
                )
            return ToolSuccess(
                _format_search_results(result.stdout, pattern, max_results, project_ctx)
            )
        elif result.returncode == 1:
            return ToolSuccess(
                f'=== SEARCH RESULTS ===\nPattern: "{pattern}"\nNo matches found.\n=== END SEARCH RESULTS ==='
            )
        else:
            return ToolError(
                f"Error: ripgrep failed with exit code {result.returncode}\n{result.stderr}",
                "execution",
            )
    except subprocess.TimeoutExpired:
        return ToolError("Error: Search timed out after 60 seconds.", "execution")
    except Exception as e:
        return ToolError(f"Error executing ripgrep: {str(e)}", "execution")


def _search_with_grep(
    pattern,
    file_pattern,
    case_sensitive,
    context_lines,
    max_results,
    abs_directory,
    project_ctx,
    output_format="full",
):
    """Fallback implementation using grep."""
    cmd = ["grep", "-r", "-E"]

    if output_format == "files_only":
        cmd.append("-l")
    elif output_format == "count":
        cmd.append("-c")
    else:
        cmd.append("-n")

    if not case_sensitive:
        cmd.append("-i")
    if context_lines > 0 and output_format == "full":
        cmd.extend(["-C", str(context_lines)])

    # Add exclusions
    for exclude_dir in [
        ".git",
        "__pycache__",
        ".venv",
        ".ayder",
        ".claude",
        "dist",
        "build",
        "htmlcov",
    ]:
        cmd.extend([f"--exclude-dir={exclude_dir}"])
    cmd.append("--exclude=*.pyc")

    # File pattern (simplified for grep)
    if file_pattern:
        include_pattern = file_pattern.split("/")[-1]
        cmd.extend(["--include", include_pattern])

    cmd.extend([pattern, str(abs_directory)])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            if output_format == "files_only":
                return ToolSuccess(
                    _format_files_only(result.stdout, pattern, project_ctx)
                )
            elif output_format == "count":
                return ToolSuccess(
                    _format_count_results(result.stdout, pattern, project_ctx)
                )
            return ToolSuccess(
                _format_grep_results(result.stdout, pattern, max_results, project_ctx)
            )
        elif result.returncode == 1:
            return ToolSuccess(
                f'=== SEARCH RESULTS ===\nPattern: "{pattern}"\nNo matches found.\n=== END SEARCH RESULTS ==='
            )
        else:
            return ToolError(
                f"Error: grep failed with exit code {result.returncode}\n{result.stderr}",
                "execution",
            )
    except subprocess.TimeoutExpired:
        return ToolError("Error: Search timed out after 60 seconds.", "execution")
    except Exception as e:
        return ToolError(f"Error executing grep: {str(e)}", "execution")


def _format_search_results(raw_output, pattern, max_results, project_ctx):
    """Format ripgrep --heading output for LLM consumption."""
    lines = raw_output.strip().split("\n")
    formatted = ["=== SEARCH RESULTS ===", f'Pattern: "{pattern}"', ""]

    current_file = None
    match_count = 0

    for line in lines:
        if match_count >= max_results:
            break

        # Ripgrep --heading format: blank line, then file path, then matches
        if not line:
            continue
        elif ":" not in line or line[0] not in "0123456789":
            # This is a file path header
            if current_file:
                formatted.append("")
            # Convert absolute path to relative
            abs_file_path = Path(line)
            try:
                rel_file = project_ctx.to_relative(abs_file_path)
            except (ValueError, TypeError) as e:
                logger.debug(f"Failed to convert path to relative: {e}")
                rel_file = line
            current_file = rel_file
            formatted.append("─" * 67)
            formatted.append(f"FILE: {current_file}")
            formatted.append("─" * 67)
        elif current_file:
            # This is a match line
            formatted.append(f"Line {line}")
            match_count += 1

    formatted.insert(2, f"Matches found: {match_count}\n")
    formatted.append("\n=== END SEARCH RESULTS ===")
    return "\n".join(formatted)


def _format_grep_results(raw_output, pattern, max_results, project_ctx):
    """Format grep output (file:line:content) for LLM consumption."""
    lines = raw_output.strip().split("\n")
    formatted = ["=== SEARCH RESULTS ===", f'Pattern: "{pattern}"', ""]

    # Group by file
    file_matches = {}
    for line in lines[:max_results]:
        if ":" in line:
            parts = line.split(":", 2)
            if len(parts) >= 3:
                file_path, line_num, content = parts[0], parts[1], parts[2]
                if file_path not in file_matches:
                    file_matches[file_path] = []
                file_matches[file_path].append((line_num, content))

    match_count = sum(len(matches) for matches in file_matches.values())
    formatted.insert(2, f"Matches found: {match_count}\n")

    for file_path, matches in file_matches.items():
        # Convert absolute path to relative
        abs_file_path = Path(file_path)
        try:
            rel_file = project_ctx.to_relative(abs_file_path)
        except (ValueError, TypeError) as e:
            logger.debug(f"Failed to convert path to relative: {e}")
            rel_file = file_path
        formatted.append("─" * 67)
        formatted.append(f"FILE: {rel_file}")
        formatted.append("─" * 67)
        for line_num, content in matches:
            formatted.append(f"Line {line_num}: {content}")
        formatted.append("")

    formatted.append("=== END SEARCH RESULTS ===")
    return "\n".join(formatted)


def _format_files_only(raw_output, pattern, project_ctx):
    """Format file-list output (one path per line) for LLM consumption."""
    lines = [line for line in raw_output.strip().split("\n") if line]
    formatted = [
        "=== SEARCH RESULTS ===",
        f'Pattern: "{pattern}"',
        f"Files with matches: {len(lines)}\n",
    ]
    for line in lines:
        abs_file_path = Path(line)
        try:
            rel_file = project_ctx.to_relative(abs_file_path)
        except (ValueError, TypeError):
            rel_file = line
        formatted.append(str(rel_file))
    formatted.append("\n=== END SEARCH RESULTS ===")
    return "\n".join(formatted)


def _format_count_results(raw_output, pattern, project_ctx):
    """Format count output (file:count per line) for LLM consumption."""
    lines = [line for line in raw_output.strip().split("\n") if line]
    formatted = ["=== SEARCH RESULTS ===", f'Pattern: "{pattern}"', ""]
    total = 0
    for line in lines:
        if ":" in line:
            file_path, count_str = line.rsplit(":", 1)
            try:
                count = int(count_str)
            except ValueError:
                continue
            total += count
            abs_file_path = Path(file_path)
            try:
                rel_file = project_ctx.to_relative(abs_file_path)
            except (ValueError, TypeError):
                rel_file = file_path
            formatted.append(f"{rel_file}: {count}")
    formatted.insert(2, f"Total matches: {total}\n")
    formatted.append("\n=== END SEARCH RESULTS ===")
    return "\n".join(formatted)
