from typing import Dict, Any, Optional
from ayder_cli.ui import draw_box
from ayder_cli.core.context import SessionContext
from .base import BaseCommand
from .registry import get_registry, CommandRegistry

# Import modules to register commands
from . import system, tools, tasks

def handle_command(cmd: str, session: SessionContext) -> bool:
    """Handle slash commands. Returns True if command was handled, False if unknown.
    
    Args:
        cmd: The command string (e.g., "/help").
        session: The session context.
    """
    # Extract command name (lowercased) and keep raw args for case-sensitive paths
    parts = cmd.split(None, 1)
    cmd_name = parts[0].lower()
    cmd_args = parts[1] if len(parts) > 1 else ""

    registry = get_registry()
    command = registry.get_command(cmd_name)
    
    if command:
        return command.execute(cmd_args, session)
    else:
        draw_box(f"Unknown command: {cmd}", title="Error", width=80, color_code="31")
        return True
