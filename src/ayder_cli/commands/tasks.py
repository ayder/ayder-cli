import shutil
import subprocess
import re
from pathlib import Path
from typing import Dict, Any, List
from ayder_cli.tasks import list_tasks, _get_task_path_by_id, _get_tasks_dir, _extract_id, _parse_title, _update_task_status
from ayder_cli.ui import draw_box
from ayder_cli.core.config import load_config
from ayder_cli.core.context import ProjectContext, SessionContext
from ayder_cli.prompts import TASK_EXECUTION_PROMPT_TEMPLATE, TASK_EXECUTION_ALL_PROMPT_TEMPLATE
from .base import BaseCommand
from .registry import register_command

@register_command
class TasksCommand(BaseCommand):
    @property
    def name(self) -> str:
        return "/tasks"
        
    @property
    def description(self) -> str:
        return "List all saved tasks"
        
    def execute(self, args: str, session: SessionContext) -> bool:
        project_ctx = session.project

        result = list_tasks(project_ctx, format="table", status="all")
        draw_box(result, title="Tasks", width=80, color_code="35")
        return True

@register_command
class TaskEditCommand(BaseCommand):
    @property
    def name(self) -> str:
        return "/task-edit"
        
    @property
    def description(self) -> str:
        return "Edit task N in your configured editor"
        
    def execute(self, args: str, session: SessionContext) -> bool:
        if not args:
            draw_box("Usage: /task-edit <task_id>\nExample: /task-edit 1", title="Error", width=80, color_code="31")
            return True

        project_ctx = session.project

        try:
            task_id = int(args.strip())
        except ValueError:
            draw_box(f"Invalid task ID: {args.strip()}\nTask ID must be a number.", title="Error", width=80, color_code="31")
            return True

        task_path = _get_task_path_by_id(project_ctx, task_id)
        if task_path is None:
            draw_box(f"Task TASK-{task_id:03d} not found.", title="Error", width=80, color_code="31")
            return True

        # Get editor from config
        # We can also use session.config if we want, but load_config is used here.
        # session.config IS available. Let's use it.
        editor = session.config.editor

        # Open editor
        try:
            subprocess.run([editor, str(task_path)], check=True)
            draw_box(f"Task TASK-{task_id:03d} edited successfully.", title="Success", width=80, color_code="32")
        except subprocess.CalledProcessError:
            draw_box(f"Error opening editor: {editor}", title="Error", width=80, color_code="31")
        except FileNotFoundError:
            draw_box(f"Editor not found: {editor}\nUpdate your config at ~/.ayder/config.toml", title="Error", width=80, color_code="31")

        return True

@register_command
class TaskRunCommand(BaseCommand):
    @property
    def name(self) -> str:
        return "/implement"

    @property
    def description(self) -> str:
        return "Run a task by ID, name, or pattern match"

    def execute(self, args: str, session: SessionContext) -> bool:
        """Execute /implement [task_id|name|pattern]

        Examples:
            /implement 099          # Run TASK-099 by ID
            /implement Flask        # Run tasks matching "Flask"
        """
        if not args:
            draw_box("Usage: /implement <task_id|name|pattern>\nExample: /implement 099",
                    title="Error", width=80, color_code="31")
            return True

        project_ctx = session.project
        tasks_dir = _get_tasks_dir(project_ctx)

        # Find matching tasks
        matching_tasks = self._find_tasks(args.strip(), tasks_dir, project_ctx)

        if not matching_tasks:
            draw_box(f"No tasks found matching: {args}", title="Error", width=80, color_code="31")
            return True

        # Show what will be run
        if len(matching_tasks) > 1:
            task_list = "\n".join([f"  - TASK-{tid:03d}: {title}" for tid, _, title in matching_tasks])
            draw_box(
                f"Found {len(matching_tasks)} matching tasks:\n{task_list}\n\n"
                f"Starting implementation...",
                title="Task Run",
                width=80,
                color_code="36"
            )

        # Run each task
        for task_id, task_path, task_title in matching_tasks:
            # Use relative path for the command
            rel_path = project_ctx.to_relative(task_path)
            command = TASK_EXECUTION_PROMPT_TEMPLATE.format(task_path=rel_path)

            draw_box(
                f"Running TASK-{task_id:03d}: {task_title}\n\n"
                f"Executing: {command[:100]}...",
                title=f"Task {task_id:03d}",
                width=80,
                color_code="33"
            )

            # Add the command as a user message to trigger LLM
            session.messages.append({"role": "user", "content": command})

        return True

    def _find_tasks(self, query: str, tasks_dir: Path, project_ctx: ProjectContext) -> List[tuple]:
        """Find tasks matching query (ID, name pattern, or keyword).

        Returns list of (task_id, task_path, task_title) tuples.
        """
        matching = []

        # Try as task ID first
        try:
            task_id = int(query)
            task_path = _get_task_path_by_id(project_ctx, task_id)
            if task_path:
                title = _parse_title(task_path)
                return [(task_id, task_path, title)]
        except ValueError:
            pass

        # Search by pattern/keyword in title
        query_lower = query.lower()
        for task_file in sorted(tasks_dir.glob("*.md")):
            task_id = _extract_id(task_file.name)
            if task_id is None:
                continue

            title = _parse_title(task_file)
            if query_lower in title.lower():
                matching.append((task_id, task_file, title))

        return matching


@register_command
class ImplementAllCommand(BaseCommand):
    @property
    def name(self) -> str:
        return "/implement-all"

    @property
    def description(self) -> str:
        return "Implement all undone tasks sequentially without stopping"

    def execute(self, args: str, session: SessionContext) -> bool:
        """Execute /implement-all

        Implements all pending tasks in sequential order, continuing
        to the next task without waiting for user review after each one.
        """
        project_ctx = session.project
        tasks_dir = _get_tasks_dir(project_ctx)

        if not tasks_dir.exists():
            draw_box("No tasks directory found. Create tasks first with /plan.",
                    title="Error", width=80, color_code="31")
            return True

        # Check if there are any pending tasks
        pending_tasks = self._find_pending_tasks(tasks_dir)

        if not pending_tasks:
            draw_box("No pending tasks found. All tasks are complete!",
                    title="Implement All", width=80, color_code="32")
            return True

        # Show what will be run
        task_list = "\n".join([f"  - TASK-{tid:03d}: {title}" for tid, _, title in pending_tasks])
        draw_box(
            f"Found {len(pending_tasks)} pending tasks to implement:\n{task_list}\n\n"
            f"Implementing all tasks sequentially...",
            title="Implement All",
            width=80,
            color_code="36"
        )

        # Add the command to implement all tasks
        command = TASK_EXECUTION_ALL_PROMPT_TEMPLATE
        session.messages.append({"role": "user", "content": command})

        return True

    def _find_pending_tasks(self, tasks_dir: Path) -> List[tuple]:
        """Find all tasks with pending/todo status.

        Returns list of (task_id, task_path, task_title) tuples sorted by ID.
        """
        pending = []

        for task_file in sorted(tasks_dir.glob("*.md")):
            task_id = _extract_id(task_file.name)
            if task_id is None:
                continue

            # Read file to check status
            content = task_file.read_text(encoding="utf-8")
            # Check for pending/todo status (case insensitive)
            if "- **status:** pending" in content.lower() or "- **status:** todo" in content.lower():
                title = _parse_title(task_file)
                pending.append((task_id, task_file, title))

        # Sort by task ID
        pending.sort(key=lambda x: x[0])
        return pending


@register_command
class ArchiveCompletedTasksCommand(BaseCommand):
    @property
    def name(self) -> str:
        return "/archive-completed-tasks"

    @property
    def description(self) -> str:
        return "Move completed (done) tasks to .ayder/task_archive"

    def execute(self, args: str, session: SessionContext) -> bool:
        project_ctx = session.project
        tasks_dir = _get_tasks_dir(project_ctx)

        if not tasks_dir.exists():
            draw_box("No tasks directory found.", title="Error", width=80, color_code="31")
            return True

        archive_dir = tasks_dir.parent / "task_archive"
        archived = []

        for task_file in sorted(tasks_dir.glob("*.md")):
            task_id = _extract_id(task_file.name)
            if task_id is None:
                continue

            content = task_file.read_text(encoding="utf-8")
            if "- **status:** done" in content.lower():
                title = _parse_title(task_file)
                archive_dir.mkdir(parents=True, exist_ok=True)
                shutil.move(str(task_file), str(archive_dir / task_file.name))
                archived.append((task_id, title))

        if not archived:
            draw_box("No completed tasks to archive.", title="Archive", width=80, color_code="33")
        else:
            lines = "\n".join(f"  TASK-{tid:03d}: {title}" for tid, title in archived)
            draw_box(
                f"Archived {len(archived)} completed task(s) to .ayder/task_archive/:\n{lines}",
                title="Archive", width=80, color_code="32"
            )

        return True
