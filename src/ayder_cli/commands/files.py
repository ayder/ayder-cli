import subprocess
from pathlib import Path
from typing import Dict, Any
from ayder_cli.ui import draw_box
from ayder_cli.core.config import load_config
from ayder_cli.core.context import SessionContext
from .base import BaseCommand
from .registry import register_command

@register_command
class EditCommand(BaseCommand):
    @property
    def name(self) -> str:
        return "/edit"
        
    @property
    def description(self) -> str:
        return "Open a file in your configured editor"
        
    def execute(self, args: str, session: SessionContext) -> bool:
        if not args:
            draw_box("Usage: /edit <file_path>\nExample: /edit src/main.py", title="Error", width=80, color_code="31")
            return True

        file_path = Path(args.strip())
        
        # Check if file exists, if not warn but allow opening (to create it)
        if not file_path.exists():
            # Maybe we should allow creating new files?
            # For now let's just warn but proceed.
            pass

        # Get editor from config
        editor = session.config.editor

        # Open editor
        try:
            subprocess.run([editor, str(file_path)], check=True)
            draw_box(f"Edited {file_path}", title="Success", width=80, color_code="32")
        except subprocess.CalledProcessError:
            draw_box(f"Error opening editor: {editor}", title="Error", width=80, color_code="31")
        except FileNotFoundError:
            draw_box(f"Editor not found: {editor}\nUpdate your config at ~/.ayder/config.toml", title="Error", width=80, color_code="31")

        return True
