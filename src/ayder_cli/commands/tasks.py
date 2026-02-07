import subprocess
from pathlib import Path
from typing import Dict, Any
from ayder_cli.tasks import list_tasks, _get_tasks_dir
from ayder_cli.ui import draw_box
from ayder_cli.core.config import load_config
from ayder_cli.core.context import ProjectContext, SessionContext
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
            
        result = list_tasks(project_ctx)
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

        task_path = _get_tasks_dir(project_ctx) / f"TASK-{task_id:03d}.md"
        if not task_path.exists():
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
