import os
import re
from datetime import datetime

TASKS_DIR = os.path.join(os.getcwd(), ".ayder", "tasks")





def _ensure_tasks_dir():
    os.makedirs(TASKS_DIR, exist_ok=True)


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
    for fname in os.listdir(TASKS_DIR):
        if fname.endswith(".md"):
            task_id = _extract_id(fname)
            if task_id is not None and task_id > max_id:
                max_id = task_id
    return max_id + 1


def create_task(title, description=""):
    """Create a task markdown file in .ayder/tasks/ (current directory)."""
    _ensure_tasks_dir()

    task_id = _next_id()
    path = os.path.join(TASKS_DIR, f"TASK-{task_id:03d}.md")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    content = f"""# {title}

- **ID:** TASK-{task_id:03d}
- **Status:** pending
- **Created:** {now}

## Description

{description if description else 'No description provided.'}
"""

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

    return f"Task TASK-{task_id:03d} created."


def _parse_status(filepath):
    """Extract the status field from a task markdown file."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                match = re.match(r"-\s+\*\*Status:\*\*\s+(.+)", line)
                if match:
                    return match.group(1).strip()
    except Exception:
        pass
    return "unknown"


def _parse_title(filepath):
    """Extract the title (first # heading) from a task markdown file."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("# "):
                    return line[2:].strip()
    except Exception:
        pass
    return os.path.basename(filepath)


def list_tasks():
    """List all tasks in .ayder/tasks/ (current directory) in a table format."""
    _ensure_tasks_dir()

    files = sorted(f for f in os.listdir(TASKS_DIR) if f.endswith(".md"))
    if not files:
        return "No tasks found."

    # Collect task data
    tasks = []
    for fname in files:
        path = os.path.join(TASKS_DIR, fname)
        task_id = _extract_id(fname)
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
    path = os.path.join(TASKS_DIR, f"TASK-{task_id:03d}.md")
    if not os.path.exists(path):
        return f"Error: Task TASK-{task_id:03d} not found."
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _update_task_status(task_id, status):
    """Update the status field of a task."""
    _ensure_tasks_dir()
    task_id = int(task_id)
    path = os.path.join(TASKS_DIR, f"TASK-{task_id:03d}.md")
    
    if not os.path.exists(path):
        return f"Error: Task TASK-{task_id:03d} not found."
    
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Replace the status line
        updated_content = re.sub(
            r"(-\s+\*\*Status:\*\*\s+)(.+)",
            rf"\1{status}",
            content
        )
        
        with open(path, "w", encoding="utf-8") as f:
            f.write(updated_content)
        
        return True
    except Exception as e:
        return f"Error updating task status: {str(e)}"


def implement_task(task_id):
    """Implement a specific task, verify, and set status to done."""
    _ensure_tasks_dir()
    task_id = int(task_id)
    path = os.path.join(TASKS_DIR, f"TASK-{task_id:03d}.md")
    
    if not os.path.exists(path):
        return f"Error: Task TASK-{task_id:03d} not found."
    
    # Check current status
    current_status = _parse_status(path)
    if current_status == "done":
        return f"Task TASK-{task_id:03d} is already completed."
    
    # Get task content
    with open(path, "r", encoding="utf-8") as f:
        task_content = f.read()
    
    # Update status to done
    result = _update_task_status(task_id, "done")
    if result is not True:
        return result
    
    return f"Task TASK-{task_id:03d} has been marked as ready to implement. Here are the details:\n\n{task_content}"


def implement_all_tasks():
    """Implement all pending tasks one by one."""
    _ensure_tasks_dir()
    
    files = sorted(f for f in os.listdir(TASKS_DIR) if f.endswith(".md"))
    if not files:
        return "No tasks found."
    
    pending_tasks = []
    for fname in files:
        path = os.path.join(TASKS_DIR, fname)
        task_id = _extract_id(fname)
        status = _parse_status(path)
        if task_id is not None and status != "done":
            pending_tasks.append((task_id, path))
    
    if not pending_tasks:
        return "No pending tasks to implement."
    
    # Sort by ID
    pending_tasks.sort(key=lambda t: t[0])
    
    results = []
    for task_id, path in pending_tasks:
        with open(path, "r", encoding="utf-8") as f:
            task_content = f.read()
        
        results.append(f"=== Implementing TASK-{task_id:03d} ===\n{task_content}\n")
        
        # Mark as done
        _update_task_status(task_id, "done")
    
    summary = f"Found {len(pending_tasks)} pending task(s). Processing them one by one:\n\n"
    summary += "\n".join(results)
    return summary
