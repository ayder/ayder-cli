import re
from datetime import datetime
from pathlib import Path

# Module-level variable for backwards compatibility with tests
TASKS_DIR = Path.cwd() / ".ayder" / "tasks"


def _get_tasks_dir():
    """Return the tasks directory path for the current working directory."""
    return Path(TASKS_DIR) if isinstance(TASKS_DIR, str) else TASKS_DIR





def _ensure_tasks_dir():
    _get_tasks_dir().mkdir(parents=True, exist_ok=True)


def _extract_id(filename):
    """Extract the numeric ID from a filename like 'TASK-001.md'."""
    match = re.match(r"^TASK-(\d+)\.md$", filename)
    if match:
        return int(match.group(1))
    return None


def _next_id():
    """Return the next available task ID by scanning existing files."""
    _ensure_tasks_dir()
    max_id = 0
    for path in _get_tasks_dir().glob("*.md"):
        task_id = _extract_id(path.name)
        if task_id is not None and task_id > max_id:
            max_id = task_id
    return max_id + 1


def create_task(title, description=""):
    """Create a task markdown file in .ayder/tasks/ (current directory)."""
    _ensure_tasks_dir()

    task_id = _next_id()
    path = _get_tasks_dir() / f"TASK-{task_id:03d}.md"
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    content = f"""# {title}

- **ID:** TASK-{task_id:03d}
- **Status:** pending
- **Created:** {now}

## Description

{description if description else 'No description provided.'}
"""

    path.write_text(content, encoding="utf-8")

    return f"Task TASK-{task_id:03d} created."


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


def list_tasks():
    """List all tasks in .ayder/tasks/ (current directory) in a table format."""
    _ensure_tasks_dir()

    files = sorted(_get_tasks_dir().glob("*.md"))
    if not files:
        return "No tasks found."

    # Collect task data
    tasks = []
    for path in files:
        task_id = _extract_id(path.name)
        title = _parse_title(path)
        status = _parse_status(path)
        if task_id is not None:
            tasks.append((task_id, title, status))

    # Sort by ID
    tasks.sort(key=lambda t: t[0])

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
        truncated = title if len(title) <= name_w else title[:name_w - 2] + ".."
        task_label = f"TASK-{tid:03d}"
        lines.append(f"  {task_label:<{id_w}} | {truncated:<{name_w}} | {status:<{stat_w}}")

    return "\n".join(lines)


def show_task(task_id):
    """Read and return the contents of a task by its numeric ID."""
    _ensure_tasks_dir()
    task_id = int(task_id)
    path = _get_tasks_dir() / f"TASK-{task_id:03d}.md"
    if not path.exists():
        return f"Error: Task TASK-{task_id:03d} not found."
    return path.read_text(encoding="utf-8")


def _update_task_status(task_id, status):
    """Update the status field of a task."""
    _ensure_tasks_dir()
    task_id = int(task_id)
    path = _get_tasks_dir() / f"TASK-{task_id:03d}.md"
    
    if not path.exists():
        return f"Error: Task TASK-{task_id:03d} not found."
    
    try:
        content = path.read_text(encoding="utf-8")
        
        # Replace the status line
        updated_content = re.sub(
            r"(-\s+\*\*Status:\*\*\s+)(.+)",
            rf"\1{status}",
            content
        )
        
        path.write_text(updated_content, encoding="utf-8")
        
        return True
    except Exception as e:
        return f"Error updating task status: {str(e)}"


def implement_task(task_id):
    """Implement a specific task, verify, and set status to done."""
    _ensure_tasks_dir()
    task_id = int(task_id)
    path = _get_tasks_dir() / f"TASK-{task_id:03d}.md"
    
    if not path.exists():
        return f"Error: Task TASK-{task_id:03d} not found."
    
    # Check current status
    current_status = _parse_status(path)
    if current_status == "done":
        return f"Task TASK-{task_id:03d} is already completed."
    
    # Get task content
    task_content = path.read_text(encoding="utf-8")
    
    # Update status to done
    result = _update_task_status(task_id, "done")
    if result is not True:
        return result
    
    return f"Task TASK-{task_id:03d} has been marked as ready to implement. Here are the details:\n\n{task_content}"


def implement_all_tasks():
    """Implement all pending tasks one by one."""
    _ensure_tasks_dir()
    
    files = sorted(_get_tasks_dir().glob("*.md"))
    if not files:
        return "No tasks found."
    
    pending_tasks = []
    for path in files:
        task_id = _extract_id(path.name)
        status = _parse_status(path)
        if task_id is not None and status != "done":
            pending_tasks.append((task_id, path))
    
    if not pending_tasks:
        return "No pending tasks to implement."
    
    # Sort by ID
    pending_tasks.sort(key=lambda t: t[0])
    
    results = []
    for task_id, path in pending_tasks:
        task_content = path.read_text(encoding="utf-8")
        
        results.append(f"=== Implementing TASK-{task_id:03d} ===\n{task_content}\n")
        
        # Mark as done
        _update_task_status(task_id, "done")
    
    summary = f"Found {len(pending_tasks)} pending task(s). Processing them one by one:\n\n"
    summary += "\n".join(results)
    return summary
