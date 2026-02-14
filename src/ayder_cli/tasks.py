import re
from datetime import datetime
from pathlib import Path

from ayder_cli.core.context import ProjectContext
from ayder_cli.core.result import ToolSuccess, ToolError


def _get_tasks_dir(project_ctx: ProjectContext):
    """Return the tasks directory path for the current project context."""
    return project_ctx.root / ".ayder" / "tasks"


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
    matches = list(tasks_dir.glob(pattern))
    if matches:
        return matches[0]
    # Fallback: check legacy format
    legacy = tasks_dir / f"TASK-{task_id:03d}.md"
    return legacy if legacy.exists() else None


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
    except Exception:
        pass
    return "unknown"


def _parse_title(filepath):
    """Extract the title (first # heading) from a task markdown file."""
    try:
        content = Path(filepath).read_text(encoding="utf-8")
        for line in content.splitlines():
            if line.startswith("# "):
                return line[2:].strip()
    except Exception:
        pass
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

    files = sorted(_get_tasks_dir(project_ctx).glob("*.md"))
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
    tasks_dir = _get_tasks_dir(project_ctx)
    path = None

    # Strategy 1: Try as relative path from project root
    try:
        candidate = project_ctx.root / identifier
        if candidate.exists() and candidate.is_file():
            path = candidate
    except Exception:
        pass

    # Strategy 2: Try as filename in tasks dir
    if path is None:
        candidate = tasks_dir / identifier
        if candidate.exists() and candidate.is_file():
            path = candidate

    # Strategy 3: Try to extract numeric ID and lookup
    if path is None:
        # Try to extract numeric ID from identifier
        # Matches: "001", "1", "TASK-001", etc.
        id_match = re.search(r"(\d+)", identifier)
        if id_match:
            task_id = int(id_match.group(1))
            path = _get_task_path_by_id(project_ctx, task_id)

    # Strategy 4: Try as slug match
    if path is None:
        # Look for files containing the identifier as a slug
        slug_pattern = identifier.lower().strip()
        for candidate in tasks_dir.glob("*.md"):
            if slug_pattern in candidate.stem.lower():
                path = candidate
                break

    if path is None:
        return ToolError(f"Error: Task not found: {identifier}")

    try:
        return ToolSuccess(path.read_text(encoding="utf-8"))
    except Exception as e:
        return ToolError(f"Error reading task file: {str(e)}", "execution")


def _update_task_status(project_ctx: ProjectContext, task_id, status):
    """Update the status field of a task."""
    _ensure_tasks_dir(project_ctx)
    task_id = int(task_id)
    path = _get_task_path_by_id(project_ctx, task_id)

    if path is None:
        return ToolError(f"Error: Task TASK-{task_id:03d} not found.")

    try:
        content = path.read_text(encoding="utf-8")

        # Replace the status line
        updated_content = re.sub(
            r"(-\s+\*\*Status:\*\*\s+)(.+)", rf"\1{status}", content
        )

        path.write_text(updated_content, encoding="utf-8")

        return ToolSuccess("Status updated")
    except Exception as e:
        return ToolError(f"Error updating task status: {str(e)}", "execution")
