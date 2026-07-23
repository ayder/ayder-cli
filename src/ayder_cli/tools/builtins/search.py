"""
Codebase search tools for ayder-cli.
"""

import logging
import re
import shutil
import subprocess
from pathlib import Path

from ayder_cli.core.context import ProjectContext
from ayder_cli.core.result import ToolSuccess, ToolError

logger = logging.getLogger(__name__)

# Build artifacts excluded from every search.
_RG_IGNORE_GLOBS = (
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
)
_GREP_EXCLUDE_DIRS = (
    ".git",
    "__pycache__",
    ".venv",
    ".ayder",
    ".claude",
    "dist",
    "build",
    "htmlcov",
)

_TRUNCATION_HINT = (
    "Use output_format='count' for the true total, "
    "or narrow the search with file_pattern."
)


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
    The 'directory' scope may be a directory or a single file.
    Supports output_format: 'full' (default), 'files_only', 'count', 'locations'.
    """
    try:
        abs_target = project_ctx.validate_path(directory)

        if abs_target.is_file():
            target_is_file = True
        elif abs_target.is_dir():
            target_is_file = False
        else:
            rel_path = project_ctx.to_relative(abs_target)
            return ToolError(
                f"Error: '{rel_path}' does not exist. Pass an existing directory "
                f"or file path in 'directory' (e.g. directory='src/core.py' to "
                f"search one file), or scope with file_pattern.",
                "validation",
            )

        if shutil.which("rg"):
            return _search_with_ripgrep(
                pattern,
                file_pattern,
                case_sensitive,
                context_lines,
                max_results,
                abs_target,
                project_ctx,
                output_format,
                target_is_file=target_is_file,
            )
        else:
            return _search_with_grep(
                pattern,
                file_pattern,
                case_sensitive,
                context_lines,
                max_results,
                abs_target,
                project_ctx,
                output_format,
                target_is_file=target_is_file,
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
    target_is_file=False,
):
    """Implementation using ripgrep."""
    cmd = [shutil.which("rg"), "--color", "never", "--no-messages"]

    if output_format == "files_only":
        cmd.append("--files-with-matches")
    elif output_format == "count":
        # --with-filename keeps 'path:count' shape for single-file targets.
        cmd.extend(["--count", "--with-filename"])
    else:  # full, locations
        # One extra match lets the formatter tell "exactly max_results"
        # from "more were available" and say so instead of lying.
        cmd.extend(["--line-number", "--heading", "--max-count", str(max_results + 1)])

    if not case_sensitive:
        cmd.append("--ignore-case")
    if context_lines > 0 and output_format == "full":
        cmd.extend(["--context", str(context_lines)])
    if file_pattern:
        # rg matches globs against the full path under the (absolute) search
        # root, so a bare 'src/core.py' would never match. '**/' makes path
        # globs suffix-anchored, which is what "search this file" means here.
        if "/" in file_pattern and not file_pattern.startswith(("**/", "/", "!")):
            file_pattern = f"**/{file_pattern}"
        cmd.extend(["--glob", file_pattern])

    for ignore in _RG_IGNORE_GLOBS:
        cmd.extend(["--glob", ignore])

    # -e keeps patterns that start with '-' (e.g. '-> str') from being
    # parsed as flags.
    cmd.extend(["-e", pattern, str(abs_directory)])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            if output_format == "files_only":
                return ToolSuccess(
                    _format_files_only(result.stdout, pattern, project_ctx)
                )
            if output_format == "count":
                known = (
                    project_ctx.to_relative(abs_directory) if target_is_file else None
                )
                return ToolSuccess(
                    _format_count_results(
                        result.stdout, pattern, project_ctx, known_file=known
                    )
                )
            # rg omits the filename heading when given one explicit file, so
            # tell the parser what it searched.
            known = project_ctx.to_relative(abs_directory) if target_is_file else None
            files = _parse_rg_heading_output(result.stdout, known_file=known)
            # The per-file --max-count cap means totals are a floor, not exact.
            if output_format == "locations":
                return ToolSuccess(
                    _render_locations(
                        files, pattern, max_results, project_ctx, approximate=True
                    )
                )
            return ToolSuccess(
                _render_full(
                    files, pattern, max_results, project_ctx, approximate=True
                )
            )
        elif result.returncode == 1:
            return ToolSuccess(_no_matches_message(pattern))
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
    target_is_file=False,
):
    """Fallback implementation using grep."""
    notes = []
    # -H forces 'path:...' prefixes even for single-file targets.
    cmd = ["grep", "-r", "-E", "-H"]

    if output_format == "files_only":
        cmd.append("-l")
    elif output_format == "count":
        cmd.append("-c")
    else:  # full, locations
        cmd.append("-n")

    if not case_sensitive:
        cmd.append("-i")
    if context_lines > 0 and output_format == "full":
        cmd.extend(["-C", str(context_lines)])

    if file_pattern:
        # grep's --include has no path-glob support; degrade loudly, not silently.
        include_pattern = file_pattern.split("/")[-1]
        if "/" in file_pattern:
            notes.append(
                f"Note: grep fallback approximates the path glob '{file_pattern}' "
                f"to basename '{include_pattern}' (matches that name in any "
                f"directory)."
            )
        # --include must precede the --exclude options: GNU grep >= 3.6
        # searches glob-unmatched files unless the FIRST filter option is an
        # --include, so exclude-first ordering disables the filter entirely.
        cmd.extend(["--include", include_pattern])

    for exclude_dir in _GREP_EXCLUDE_DIRS:
        cmd.append(f"--exclude-dir={exclude_dir}")
    cmd.append("--exclude=*.pyc")

    # -e keeps patterns that start with '-' from being parsed as flags.
    cmd.extend(["-e", pattern, str(abs_directory)])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            if output_format == "files_only":
                return ToolSuccess(
                    _format_files_only(result.stdout, pattern, project_ctx, notes)
                )
            if output_format == "count":
                return ToolSuccess(
                    _format_count_results(result.stdout, pattern, project_ctx, notes)
                )
            files = _parse_grep_output(
                result.stdout, abs_target=abs_directory, target_is_file=target_is_file
            )
            if output_format == "locations":
                return ToolSuccess(
                    _render_locations(
                        files, pattern, max_results, project_ctx, notes=notes
                    )
                )
            return ToolSuccess(
                _render_full(files, pattern, max_results, project_ctx, notes=notes)
            )
        elif result.returncode == 1:
            return ToolSuccess(_no_matches_message(pattern, notes))
        else:
            return ToolError(
                f"Error: grep failed with exit code {result.returncode}\n{result.stderr}",
                "execution",
            )
    except subprocess.TimeoutExpired:
        return ToolError("Error: Search timed out after 60 seconds.", "execution")
    except Exception as e:
        return ToolError(f"Error executing grep: {str(e)}", "execution")


def _parse_rg_heading_output(raw_output, known_file=None):
    """Parse rg --heading output into [(file_path, entries)].

    Each entry is (line_no, kind, text) with kind in 'match' | 'context' |
    'separator'. In heading mode a block starts with the file path and blank
    lines separate blocks, so headers are identified by position — never by
    guessing from content (which broke on context lines like '294-' and on
    '--' group separators). known_file covers single-file targets, where rg
    omits the heading entirely.
    """
    files = []
    entries = None
    in_block = False
    if known_file is not None:
        entries = []
        files.append((known_file, entries))
        in_block = True

    for line in raw_output.split("\n"):
        if line == "":
            if known_file is None:
                in_block = False
            continue
        if not in_block:
            entries = []
            files.append((line, entries))
            in_block = True
            continue
        if line == "--":
            entries.append((None, "separator", ""))
            continue
        m = re.match(r"^(\d+)([:-])(.*)$", line)
        if m:
            kind = "match" if m.group(2) == ":" else "context"
            entries.append((m.group(1), kind, m.group(3)))
        else:
            # Unexpected shape inside a block; keep it visible rather than drop it.
            entries.append((None, "context", line))
    return files


def _parse_grep_output(raw_output, abs_target=None, target_is_file=False):
    """Parse grep -H output ('path:line:content', context 'path-line-content')
    into the same [(file_path, entries)] structure as the rg parser.

    The ':' form is tried before the '-' form so directory names containing
    '-<digits>-' can't steal a match line; context lines in such paths remain
    a best-effort parse on this fallback engine.
    """
    by_path = {}
    order = []
    prefix = str(abs_target) if target_is_file and abs_target is not None else None

    def entry_list(path):
        if path not in by_path:
            by_path[path] = []
            order.append(path)
        return by_path[path]

    for line in raw_output.split("\n"):
        if not line:
            continue
        if line == "--":
            if order:
                by_path[order[-1]].append((None, "separator", ""))
            continue
        if prefix is not None and line.startswith(prefix):
            rest = line[len(prefix) :]
            m = re.match(r"^([:-])(\d+)\1(.*)$", rest)
            if not m:
                continue
            sep, line_no, text = m.group(1), m.group(2), m.group(3)
            path = prefix
        else:
            m = re.match(r"^(.*?):(\d+):(.*)$", line)
            if m:
                path, line_no, text = m.groups()
                sep = ":"
            else:
                m = re.match(r"^(.*?)-(\d+)-(.*)$", line)
                if not m:
                    continue
                path, line_no, text = m.groups()
                sep = "-"
        kind = "match" if sep == ":" else "context"
        entry_list(path).append((line_no, kind, text))

    return [(path, by_path[path]) for path in order]


def _render_full(files, pattern, max_results, project_ctx, approximate=False, notes=()):
    """Render parsed results as headed blocks of matching lines."""
    total = sum(1 for _, entries in files for e in entries if e[1] == "match")
    truncated = total > max_results
    plus = "+" if truncated and approximate else ""

    formatted = ["=== SEARCH RESULTS ===", f'Pattern: "{pattern}"']
    formatted.extend(notes)
    if truncated:
        formatted.append(f"Matches found: {total}{plus} (showing first {max_results})")
    else:
        formatted.append(f"Matches found: {total}")
    formatted.append("")

    shown = 0
    for file_path, entries in files:
        if shown >= max_results:
            break
        rel_file = _to_rel(file_path, project_ctx)
        formatted.append("─" * 67)
        formatted.append(f"FILE: {rel_file}")
        formatted.append("─" * 67)
        for line_no, kind, text in entries:
            if kind == "match":
                if shown >= max_results:
                    break
                formatted.append(f"Line {line_no}: {text}")
                shown += 1
            elif kind == "separator":
                formatted.append("  --")
            elif line_no is not None:
                formatted.append(f"  {line_no}- {text}")
            else:
                formatted.append(f"  {text}")
        formatted.append("")

    if truncated:
        formatted.append(
            f"[Results truncated: showing first {max_results} of {total}{plus} "
            f"matches. {_TRUNCATION_HINT}]"
        )
    formatted.append("\n=== END SEARCH RESULTS ===")
    return "\n".join(formatted)


def _render_locations(
    files, pattern, max_results, project_ctx, approximate=False, notes=()
):
    """Render parsed results as 'file: line, line, ...' — where without what."""
    total = sum(1 for _, entries in files for e in entries if e[1] == "match")
    truncated = total > max_results
    plus = "+" if truncated and approximate else ""

    formatted = ["=== SEARCH RESULTS ===", f'Pattern: "{pattern}"']
    formatted.extend(notes)
    if total == 0:
        formatted.append("No matches found.")
        formatted.append("=== END SEARCH RESULTS ===")
        return "\n".join(formatted)

    formatted.append(f"Matches found: {total}{plus} in {len(files)} file(s)")
    formatted.append("")

    shown = 0
    for file_path, entries in files:
        if shown >= max_results:
            break
        line_numbers = []
        for line_no, kind, _ in entries:
            if kind != "match":
                continue
            if shown >= max_results:
                break
            line_numbers.append(line_no)
            shown += 1
        if line_numbers:
            rel_file = _to_rel(file_path, project_ctx)
            formatted.append(f"{rel_file}: {', '.join(line_numbers)}")

    if truncated:
        formatted.append("")
        formatted.append(
            f"[Results truncated: showing first {max_results} of {total}{plus} "
            f"matches. {_TRUNCATION_HINT}]"
        )
    formatted.append("\n=== END SEARCH RESULTS ===")
    return "\n".join(formatted)


def _no_matches_message(pattern, notes=()):
    parts = ["=== SEARCH RESULTS ===", f'Pattern: "{pattern}"']
    parts.extend(notes)
    parts.append("No matches found.")
    parts.append("=== END SEARCH RESULTS ===")
    return "\n".join(parts)


def _format_files_only(raw_output, pattern, project_ctx, notes=()):
    """Format file-list output (one path per line) for LLM consumption."""
    lines = [line for line in raw_output.strip().split("\n") if line]
    formatted = ["=== SEARCH RESULTS ===", f'Pattern: "{pattern}"']
    formatted.extend(notes)
    formatted.append(f"Files with matches: {len(lines)}\n")
    for line in lines:
        formatted.append(_to_rel(line, project_ctx))
    formatted.append("\n=== END SEARCH RESULTS ===")
    return "\n".join(formatted)


def _format_count_results(raw_output, pattern, project_ctx, notes=(), known_file=None):
    """Format count output (file:count per line) for LLM consumption.

    Files with zero matches (grep -c lists every file scanned) are omitted.
    known_file names the target when the engine printed a bare count for a
    single-file search.
    """
    lines = [line for line in raw_output.strip().split("\n") if line]
    entries = []
    total = 0
    for line in lines:
        if known_file is not None and line.isdigit():
            rel_file, count = known_file, int(line)
        elif ":" in line:
            file_path, count_str = line.rsplit(":", 1)
            try:
                count = int(count_str)
            except ValueError:
                continue
            rel_file = _to_rel(file_path, project_ctx)
        else:
            continue
        if count == 0:
            continue
        total += count
        entries.append(f"{rel_file}: {count}")

    formatted = ["=== SEARCH RESULTS ===", f'Pattern: "{pattern}"']
    formatted.extend(notes)
    formatted.append(f"Total matches: {total}\n")
    formatted.extend(entries)
    formatted.append("\n=== END SEARCH RESULTS ===")
    return "\n".join(formatted)


def _format_search_results(raw_output, pattern, max_results, project_ctx):
    """Format raw rg --heading output as a full result block."""
    files = _parse_rg_heading_output(raw_output)
    return _render_full(files, pattern, max_results, project_ctx, approximate=True)


def _format_grep_results(raw_output, pattern, max_results, project_ctx):
    """Format raw grep output (file:line:content) as a full result block."""
    files = _parse_grep_output(raw_output)
    return _render_full(files, pattern, max_results, project_ctx)


def _to_rel(path_str, project_ctx):
    """Best-effort conversion to a project-relative path for display."""
    try:
        return project_ctx.to_relative(Path(path_str))
    except (ValueError, TypeError) as e:
        logger.debug(f"Failed to convert path to relative: {e}")
        return str(path_str)
