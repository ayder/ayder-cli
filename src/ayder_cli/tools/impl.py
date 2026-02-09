"""
Tool implementation functions for ayder-cli.

This module contains the actual implementation of all file system and code navigation tools.
"""

import json
import logging
import os
import subprocess
import shutil
from pathlib import Path
from ayder_cli.core.context import ProjectContext
from ayder_cli.core.result import ToolSuccess, ToolError

logger = logging.getLogger(__name__)


# --- Constants ---

# Maximum file size allowed for read_file() to prevent DoS/memory exhaustion
# Default: 10MB
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 megabytes


# --- Tool Implementations ---

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

def read_file(project_ctx: ProjectContext, file_path: str, start_line: int = None, end_line: int = None) -> str:
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
            return ToolError(f"Error: File '{rel_path}' is too large ({file_size / (1024 * 1024):.1f}MB). Maximum allowed size is {MAX_FILE_SIZE / (1024 * 1024):.0f}MB.")

        with open(abs_path, 'r', encoding='utf-8') as f:
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

        with open(abs_path, 'w', encoding='utf-8') as f:
            f.write(content)

        rel_path = project_ctx.to_relative(abs_path)
        return ToolSuccess(f"Successfully wrote to {rel_path}")

    except ValueError as e:
        return ToolError(f"Security Error: {str(e)}", "security")
    except Exception as e:
        return ToolError(f"Error writing file: {str(e)}", "execution")

def replace_string(project_ctx: ProjectContext, file_path: str, old_string: str, new_string: str) -> str:
    """Replaces a specific string in a file with a new string."""
    try:
        abs_path = project_ctx.validate_path(file_path)

        with open(abs_path, 'r', encoding='utf-8') as f:
            content = f.read()

        if old_string not in content:
            rel_path = project_ctx.to_relative(abs_path)
            return ToolError(f"Error: 'old_string' not found in {rel_path}. No changes made.")

        new_content = content.replace(old_string, new_string)

        with open(abs_path, 'w', encoding='utf-8') as f:
            f.write(new_content)

        rel_path = project_ctx.to_relative(abs_path)
        return ToolSuccess(f"Successfully replaced text in {rel_path}")

    except ValueError as e:
        return ToolError(f"Security Error: {str(e)}", "security")
    except Exception as e:
        return ToolError(f"Error replacing text: {str(e)}", "execution")

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
            cwd=str(project_ctx.root)
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

def get_project_structure(project_ctx: ProjectContext, max_depth: int = 3) -> str:
    """Generate a tree-style project structure summary using project root."""
    tree_path = shutil.which("tree")

    if tree_path:
        cmd = [
            tree_path, "-L", str(max_depth),
            "-I", "__pycache__|*.pyc|*.egg-info|.venv|.ayder|.claude|htmlcov|dist|build",
            "--charset", "ascii", "--noreport"
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5, cwd=str(project_ctx.root))
            if result.returncode == 0:
                return ToolSuccess(result.stdout.strip())
        except Exception:
            pass

    # Fallback to manual tree generation
    return ToolSuccess(_generate_manual_tree(project_ctx, max_depth))


def _generate_manual_tree(project_ctx: ProjectContext, max_depth: int = 3) -> str:
    """Fallback manual tree generator using project root."""
    IGNORE_DIRS = {"__pycache__", ".venv", ".ayder", ".claude", ".git", "htmlcov", "dist", "build", "node_modules"}
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

def insert_line(project_ctx: ProjectContext, file_path: str, line_number: int, content: str) -> str:
    """Insert content at a specific line number in a file."""
    try:
        abs_path = project_ctx.validate_path(file_path)

        if not abs_path.exists():
            rel_path = project_ctx.to_relative(abs_path)
            return ToolError(f"Error: File '{rel_path}' does not exist.")

        with open(abs_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        if line_number < 1:
            return ToolError("Error: line_number must be >= 1.", "validation")

        # Clamp to append if beyond end
        idx = min(line_number - 1, len(lines))

        # Ensure content ends with newline
        if content and not content.endswith('\n'):
            content += '\n'

        lines.insert(idx, content)

        with open(abs_path, 'w', encoding='utf-8') as f:
            f.writelines(lines)

        rel_path = project_ctx.to_relative(abs_path)
        return ToolSuccess(f"Successfully inserted content at line {line_number} in {rel_path}")

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

        with open(abs_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        if line_number < 1 or line_number > len(lines):
            return ToolError(f"Error: line_number {line_number} is out of range (1-{len(lines)}).", "validation")

        deleted = lines.pop(line_number - 1)

        with open(abs_path, 'w', encoding='utf-8') as f:
            f.writelines(lines)

        rel_path = project_ctx.to_relative(abs_path)
        preview = deleted.rstrip('\n')[:80]
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
                with open(abs_path, 'r', encoding='utf-8', errors='replace') as f:
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


def search_codebase(project_ctx: ProjectContext, pattern: str, file_pattern: str = None,
                   case_sensitive: bool = True, context_lines: int = 0,
                   max_results: int = 50, directory: str = ".", output_format: str = "full") -> str:
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
            return _search_with_ripgrep(pattern, file_pattern, case_sensitive,
                                       context_lines, max_results, abs_dir, project_ctx, output_format)
        else:
            return _search_with_grep(pattern, file_pattern, case_sensitive,
                                    context_lines, max_results, abs_dir, project_ctx, output_format)
    except ValueError as e:
        return ToolError(f"Security Error: {str(e)}", "security")
    except Exception as e:
        return ToolError(f"Error during search: {str(e)}", "execution")


def _search_with_ripgrep(pattern, file_pattern, case_sensitive,
                        context_lines, max_results, abs_directory, project_ctx,
                        output_format="full"):
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
    for ignore in ["!.git/", "!__pycache__/", "!*.pyc", "!.venv/", "!.ayder/",
                   "!.claude/", "!dist/", "!build/", "!*.egg-info/", "!htmlcov/"]:
        cmd.extend(["--glob", ignore])

    cmd.extend([pattern, str(abs_directory)])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            if output_format == "files_only":
                return ToolSuccess(_format_files_only(result.stdout, pattern, project_ctx))
            elif output_format == "count":
                return ToolSuccess(_format_count_results(result.stdout, pattern, project_ctx))
            return ToolSuccess(_format_search_results(result.stdout, pattern, max_results, project_ctx))
        elif result.returncode == 1:
            return ToolSuccess(f"=== SEARCH RESULTS ===\nPattern: \"{pattern}\"\nNo matches found.\n=== END SEARCH RESULTS ===")
        else:
            return ToolError(f"Error: ripgrep failed with exit code {result.returncode}\n{result.stderr}", "execution")
    except subprocess.TimeoutExpired:
        return ToolError("Error: Search timed out after 60 seconds.", "execution")
    except Exception as e:
        return ToolError(f"Error executing ripgrep: {str(e)}", "execution")


def _search_with_grep(pattern, file_pattern, case_sensitive,
                     context_lines, max_results, abs_directory, project_ctx,
                     output_format="full"):
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
    for exclude_dir in [".git", "__pycache__", ".venv", ".ayder", ".claude",
                       "dist", "build", "htmlcov"]:
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
                return ToolSuccess(_format_files_only(result.stdout, pattern, project_ctx))
            elif output_format == "count":
                return ToolSuccess(_format_count_results(result.stdout, pattern, project_ctx))
            return ToolSuccess(_format_grep_results(result.stdout, pattern, max_results, project_ctx))
        elif result.returncode == 1:
            return ToolSuccess(f"=== SEARCH RESULTS ===\nPattern: \"{pattern}\"\nNo matches found.\n=== END SEARCH RESULTS ===")
        else:
            return ToolError(f"Error: grep failed with exit code {result.returncode}\n{result.stderr}", "execution")
    except subprocess.TimeoutExpired:
        return ToolError("Error: Search timed out after 60 seconds.", "execution")
    except Exception as e:
        return ToolError(f"Error executing grep: {str(e)}", "execution")


def _format_search_results(raw_output, pattern, max_results, project_ctx):
    """Format ripgrep --heading output for LLM consumption."""
    lines = raw_output.strip().split('\n')
    formatted = ["=== SEARCH RESULTS ===", f"Pattern: \"{pattern}\"", ""]

    current_file = None
    match_count = 0

    for line in lines:
        if match_count >= max_results:
            break

        # Ripgrep --heading format: blank line, then file path, then matches
        if not line:
            continue
        elif ':' not in line or line[0] not in '0123456789':
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
    lines = raw_output.strip().split('\n')
    formatted = ["=== SEARCH RESULTS ===", f"Pattern: \"{pattern}\"", ""]

    # Group by file
    file_matches = {}
    for line in lines[:max_results]:
        if ':' in line:
            parts = line.split(':', 2)
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
    lines = [l for l in raw_output.strip().split('\n') if l]
    formatted = ["=== SEARCH RESULTS ===", f"Pattern: \"{pattern}\"",
                 f"Files with matches: {len(lines)}\n"]
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
    lines = [l for l in raw_output.strip().split('\n') if l]
    formatted = ["=== SEARCH RESULTS ===", f"Pattern: \"{pattern}\"", ""]
    total = 0
    for line in lines:
        if ':' in line:
            file_path, count_str = line.rsplit(':', 1)
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