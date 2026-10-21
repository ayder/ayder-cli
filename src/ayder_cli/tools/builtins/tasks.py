import re
import threading
from datetime import datetime
from pathlib import Path

from ayder_cli.core.context import ProjectContext
from ayder_cli.core.result import ToolSuccess, ToolError
from ayder_cli.log import get_logger

logger = get_logger("tool")

# Serializes task-id allocation + file claim across the agent harness's
# worker threads (tool handlers run in asyncio.to_thread). _next_id is a
# scan-max+1 read and the on-disk uniqueness guard is per-filename (slug), so
# two concurrent creates with different titles would otherwise allocate the same
# id and write distinct filenames -> duplicate TASK-NNN. Hold this across the
# whole allocate-then-write critical section. Shared by create_task (here) and
# task_tool._create.
_ID_LOCK = threading.Lock()


def _get_tasks_dir(project_ctx: ProjectContext) -> Path:
    """Return the tasks directory, refusing one that resolves outside the root.

    Raises:
        ValueError: If ``.ayder/tasks`` resolves outside the project root.
    """
    return project_ctx.harness_dir("tasks")


def _confined_task_files(tasks_dir: Path):
    """Yield ``tasks_dir/*.md`` in sorted order, skipping any that resolve outside.

    An outward symlink is omitted before it is read or stat-ed. Yielded paths
    keep their own names, so ids and relative paths stay stable.
    """
    for path in sorted(tasks_dir.glob("*.md")):
        try:
            yield ProjectContext.within(tasks_dir, path)
        except ValueError:
            continue


def _ensure_tasks_dir(project_ctx: ProjectContext):
    _get_tasks_dir(project_ctx).mkdir(parents=True, exist_ok=True)


def _title_to_slug(title: str) -> str:
    """Convert title to kebab-case slug for filenames.

    Rules:
    - Lowercase
    - Replace whitespace and special chars with hyphens
    - Collapse consecutive hyphens
    - Strip leading/trailing hyphens
    - Truncate to 30 chars (at word boundary if possible)
    - Fall back to 'untitled' if empty after sanitization
    """
    slug = title.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    if len(slug) > 30:
        truncated = slug[:30].rsplit("-", 1)[0]
        slug = truncated if truncated else slug[:30]
    return slug or "untitled"


def _extract_id(filename):
    """Extract numeric ID from 'TASK-001-some-slug.md' or legacy 'TASK-001.md'."""
    match = re.match(r"^TASK-(\d+)(?:-.+)?\.md$", filename)
    if match:
        return int(match.group(1))
    return None


def _get_task_path_by_id(project_ctx: ProjectContext, task_id: int):
    """Find a task file by its numeric ID using glob pattern."""
    tasks_dir = _get_tasks_dir(project_ctx)
    pattern = f"TASK-{task_id:03d}-*.md"
    for match in sorted(tasks_dir.glob(pattern)):
        try:
            return ProjectContext.within(tasks_dir, match)
        except ValueError:
            continue
    # Fallback: check legacy format
    legacy = tasks_dir / f"TASK-{task_id:03d}.md"
    if not legacy.exists():
        return None
    try:
        return ProjectContext.within(tasks_dir, legacy)
    except ValueError:
        return None


def _next_id(project_ctx: ProjectContext):
    """Return the next available task ID by scanning existing files."""
    _ensure_tasks_dir(project_ctx)
    max_id = 0
    for path in _get_tasks_dir(project_ctx).glob("*.md"):
        task_id = _extract_id(path.name)
        if task_id is not None and task_id > max_id:
            max_id = task_id
    return max_id + 1


def create_task(project_ctx: ProjectContext, title: str, description: str = ""):
    """Create a task markdown file in .ayder/tasks/ (current directory)."""
    _ensure_tasks_dir(project_ctx)

    with _ID_LOCK:
        task_id = _next_id(project_ctx)
        slug = _title_to_slug(title)
        path = _get_tasks_dir(project_ctx) / f"TASK-{task_id:03d}-{slug}.md"
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        content = f"""# {title}

- **ID:** TASK-{task_id:03d}
- **Status:** pending
- **Created:** {now}

## Description

{description if description else "No description provided."}
"""

        path.write_text(content, encoding="utf-8")

    return ToolSuccess(f"Task TASK-{task_id:03d} created.")


def _parse_status(filepath):
    """Extract the status field from a task markdown file."""
    try:
        content = Path(filepath).read_text(encoding="utf-8")
        for line in content.splitlines():
            match = re.match(r"-\s+\*\*Status:\*\*\s+(.+)", line)
            if match:
                return match.group(1).strip()
    except Exception:  # noqa: BLE001 - best-effort parse: an unreadable or malformed task file yields "unknown", not an error
        logger.opt(exception=True).debug("Failed to parse status from {}", filepath)
    return "unknown"


def _parse_title(filepath):
    """Extract the title (first # heading) from a task markdown file."""
    try:
        content = Path(filepath).read_text(encoding="utf-8")
        for line in content.splitlines():
            if line.startswith("# "):
                return line[2:].strip()
    except Exception:  # noqa: BLE001 - best-effort parse: an unreadable or malformed task file falls back to the filename
        logger.opt(exception=True).debug("Failed to parse title from {}", filepath)
    return Path(filepath).name


def list_tasks(
    project_ctx: ProjectContext, format: str = "list", status: str = "pending"
):
    """List tasks in .ayder/tasks/ (current directory), filtered by status.

    Args:
        project_ctx: Project context for path resolution
        format: Output format - "list" returns filenames, "table" returns formatted table
        status: Filter by status - "pending", "done", or "all" (default: "pending")

    Returns:
        ToolSuccess with newline-separated task file paths (format="list")
        or formatted table (format="table")
    """
    _ensure_tasks_dir(project_ctx)

    files = list(_confined_task_files(_get_tasks_dir(project_ctx)))
    if not files:
        return ToolSuccess("No tasks found.")

    # Collect task data (uniform 3-tuples: id, name, status)
    tasks: list[tuple[int, str, str]] = []
    for path in files:
        task_id = _extract_id(path.name)
        if task_id is not None:
            task_status = _parse_status(path)

            # Filter by status
            if status != "all" and task_status.lower() != status.lower():
                continue

            if format == "list":
                # Return relative path from project root
                rel_path = path.relative_to(project_ctx.root)
                tasks.append((task_id, str(rel_path), ""))
            else:
                title = _parse_title(path)
                tasks.append((task_id, title, task_status))

    # Check if any tasks matched the filter
    if not tasks:
        filter_msg = f" with status '{status}'" if status != "all" else ""
        return ToolSuccess(f"No tasks found{filter_msg}.")

    # Sort by ID
    tasks.sort(key=lambda t: t[0])

    if format == "list":
        # Simple newline-separated list of relative paths
        return ToolSuccess("\n".join(t[1] for t in tasks))

    # Table format (for /tasks command)
    # Calculate column widths
    id_w = max(len("Task ID"), max(len(f"TASK-{t[0]:03d}") for t in tasks))
    name_w = max(len("Task Name"), max(len(t[1]) for t in tasks))
    stat_w = max(len("Status"), max(len(t[2]) for t in tasks))

    # Cap name width to keep table within 72 chars
    max_name = 72 - id_w - stat_w - 10  # 10 for separators/padding
    if name_w > max_name:
        name_w = max(max_name, 10)

    sep = f" {'-' * (id_w + 2)}+{'-' * (name_w + 2)}+{'-' * (stat_w + 2)}"
    header = f"  {'Task ID':<{id_w}} | {'Task Name':<{name_w}} | {'Status':<{stat_w}}"

    lines = [header, sep]
    for tid, title, status in tasks:
        truncated = title if len(title) <= name_w else title[: name_w - 2] + ".."
        task_label = f"TASK-{tid:03d}"
        lines.append(
            f"  {task_label:<{id_w}} | {truncated:<{name_w}} | {status:<{stat_w}}"
        )

    return ToolSuccess("\n".join(lines))


_ID_FORM = re.compile(r"^(?:TASK-)?0*(\d+)(?:\.md)?$", re.IGNORECASE)


def _slug_matches(tasks_dir: Path, pattern: str) -> list[Path]:
    """Return the tasks whose slug equals ``pattern``, else those containing it.

    The slug is the stem after ``TASK-NNN-``; ``pattern`` is lower-case.
    """
    files = list(_confined_task_files(tasks_dir))
    exact = [p for p in files if re.fullmatch(rf"task-\d+-{re.escape(pattern)}", p.stem.lower())]
    return exact or [p for p in files if pattern in p.stem.lower()]


def resolve_task_path(project_ctx: ProjectContext, identifier: str) -> Path | None:
    """Resolve a task identifier to its file path, or None if no task matches.

    Tries, in order: relative path from project root, filename in the tasks dir,
    numeric ID lookup ("001"/"1"/"TASK-001"), then slug match. An ID-form
    identifier matches only that ID; a slug must match exactly one task (an
    exact slug beats a substring). Shared
    by the `task` tool and the agent harness (which resolves the agent tool's
    task_id), so both accept identifiers in the same flexible forms.

    Every result must resolve inside ``.ayder/tasks``. A path-form identifier
    that exists but escapes ends resolution with ``None`` instead of falling
    through to the fuzzy id and slug strategies. An unconfined tasks dir
    yields ``None``.
    """
    try:
        tasks_dir = _get_tasks_dir(project_ctx)
    except ValueError:
        return None
    identifier = identifier.strip()

    def _confined(path: Path) -> Path | None:
        try:
            return ProjectContext.within(tasks_dir, path)
        except ValueError:
            return None

    # Strategy 1: Try as relative path from project root
    found: Path | None = None
    try:
        candidate = project_ctx.root / identifier
        if candidate.exists() and candidate.is_file():
            found = candidate
    except Exception:  # noqa: BLE001 - resolver strategy 1 of several: any failure must fall through to the next strategy
        logger.opt(exception=True).debug(
            "Strategy 1 (relative path) failed ({} chars)", len(identifier)
        )

    if found is not None:
        return _confined(found)

    # Strategy 2: Try as filename in tasks dir
    candidate = tasks_dir / identifier
    if candidate.exists() and candidate.is_file():
        return _confined(candidate)

    # Strategy 3: an ID form ("001", "1", "TASK-001") never falls through
    id_match = _ID_FORM.fullmatch(identifier)
    if id_match:
        return _get_task_path_by_id(project_ctx, int(id_match.group(1)))

    # Strategy 4: a slug that matches exactly one task
    if identifier:
        matches = _slug_matches(tasks_dir, identifier.lower())
        if len(matches) == 1:
            return matches[0]

    return None


def ambiguous_task_ids(project_ctx: ProjectContext, identifier: str) -> list[str]:
    """Return the IDs a slug identifier matches when it matches two or more tasks."""
    try:
        tasks_dir = _get_tasks_dir(project_ctx)
    except ValueError:
        return []
    identifier = identifier.strip()
    if not identifier or _ID_FORM.fullmatch(identifier):
        return []
    matches = _slug_matches(tasks_dir, identifier.lower())
    if len(matches) < 2:
        return []
    ids = []
    for path in matches:
        num = _extract_id(path.name)
        ids.append(f"TASK-{num:03d}" if num is not None else path.stem)
    return ids


def read_task(project_ctx: ProjectContext, identifier: str):
    """Resolve a task identifier and read its file.

    Returns a (canonical_id, project_relative_path, content) tuple, or None when
    the identifier resolves to no task / cannot be read. canonical_id is the
    "TASK-NNN" form when derivable from the filename, else the file stem.
    """
    path = resolve_task_path(project_ctx, identifier)
    if path is None:
        return None
    try:
        content = path.read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001 - best-effort read: an unreadable task file yields no signature rather than raising
        logger.opt(exception=True).warning("Failed to read task file {}", path)
        return None
    tid = _extract_id(path.name)
    canonical = f"TASK-{tid:03d}" if tid is not None else path.stem
    try:
        rel = str(path.relative_to(project_ctx.root))
    except ValueError:
        rel = str(path)
    return canonical, rel, content


def list_task_ids(project_ctx: ProjectContext) -> list[str]:
    """Return the canonical IDs ("TASK-NNN") of every task file, sorted."""
    ids: list[str] = []
    try:
        tasks_dir = _get_tasks_dir(project_ctx)
    except ValueError:
        return ids
    for path in _confined_task_files(tasks_dir):
        tid = _extract_id(path.name)
        if tid is not None:
            ids.append(f"TASK-{tid:03d}")
    return ids


def show_task(project_ctx: ProjectContext, identifier: str):
    """Read and return the contents of a task file.

    Args:
        project_ctx: Project context for path resolution
        identifier: Can be:
            - Relative path: ".ayder/tasks/TASK-001-add-auth.md"
            - Filename: "TASK-001-add-auth.md"
            - Task ID: "001" or "1" or "TASK-001"
            - Slug: "add-auth"

    Returns:
        ToolSuccess with file contents or ToolError if not found
    """
    _ensure_tasks_dir(project_ctx)
    path = resolve_task_path(project_ctx, identifier)

    if path is None:
        return ToolError(f"Error: Task not found: {identifier}")

    try:
        return ToolSuccess(path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001 - tool boundary: any task-file read failure becomes a ToolError, since tools must not raise into the loop
        return ToolError(f"Error reading task file: {str(e)}", "execution")


def update_task_temporal_metadata(
    project_ctx: ProjectContext,
    task_id: int,
    workflow_id: str,
    report_path: str,
    origin_queue: str,
    status: str,
):
    """Append or update a Temporal metadata section in a task markdown file."""
    _ensure_tasks_dir(project_ctx)
    path = _get_task_path_by_id(project_ctx, int(task_id))

    if path is None:
        return ToolError(f"Error: Task TASK-{int(task_id):03d} not found.")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    temporal_block = (
        "## Temporal\n\n"
        f"- **Workflow ID:** {workflow_id}\n"
        f"- **Origin Queue:** {origin_queue}\n"
        f"- **Status:** {status}\n"
        f"- **Report Path:** {report_path}\n"
        f"- **Updated:** {now}\n"
    )

    try:
        content = path.read_text(encoding="utf-8")

        if re.search(r"\n## Temporal\n", content):
            updated = re.sub(
                r"\n## Temporal\n.*?(?=\n## |\Z)",
                "\n" + temporal_block + "\n",
                content,
                flags=re.DOTALL,
            )
        else:
            updated = content.rstrip() + "\n\n" + temporal_block + "\n"

        path.write_text(updated, encoding="utf-8")
        return ToolSuccess("Task temporal metadata updated")
    except Exception as e:  # noqa: BLE001 - tool boundary: rewriting a model-supplied task file must fail as a ToolError, never as a crash
        return ToolError(f"Error updating task temporal metadata: {e}", "execution")
