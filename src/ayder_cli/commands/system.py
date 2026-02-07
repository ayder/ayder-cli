from typing import Dict, Any
from ayder_cli.ui import draw_box
from ayder_cli.core.context import SessionContext
from .base import BaseCommand
from .registry import register_command, get_registry

@register_command
class HelpCommand(BaseCommand):
    @property
    def name(self) -> str:
        return "/help"
        
    @property
    def description(self) -> str:
        return "Show this help message"
        
    def execute(self, args: str, session: SessionContext) -> bool:
        commands = get_registry().list_commands()
        # Sort by name
        commands.sort(key=lambda c: c.name)
        
        help_text = "Available Commands:\n"
        for cmd in commands:
            help_text += f"  {cmd.name:<15} - {cmd.description}\n"
            
        draw_box(help_text, title="Help", width=80, color_code="33")
        return True

@register_command
class ClearCommand(BaseCommand):
    @property
    def name(self) -> str:
        return "/clear"

    @property
    def description(self) -> str:
        return "Clear conversation history and reset context"

    def execute(self, args: str, session: SessionContext) -> bool:
        # Clear messages but keep system prompt if present
        messages = session.messages
        if messages:
            # We assume the first message is system prompt if it exists
            if messages[0].get("role") == "system":
                system_msg = messages[0]
                messages.clear()
                messages.append(system_msg)
            else:
                messages.clear()
                
        draw_box("Conversation history cleared.", title="System", width=80, color_code="32")
        return True

@register_command
class VerboseCommand(BaseCommand):
    @property
    def name(self) -> str:
        return "/verbose"

    @property
    def description(self) -> str:
        return "Toggle verbose mode"

    def execute(self, args: str, session: SessionContext) -> bool:
        current = session.state.get("verbose", False)
        session.state["verbose"] = not current
        status = "ON" if session.state["verbose"] else "OFF"
        draw_box(f"Verbose mode: {status}", title="System", width=80, color_code="34")
        return True
