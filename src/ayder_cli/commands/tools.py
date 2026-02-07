from typing import Dict, Any
from ayder_cli.tools.schemas import tools_schema
from ayder_cli.ui import draw_box
from ayder_cli.core.context import SessionContext
from .base import BaseCommand
from .registry import register_command

@register_command
class ToolsCommand(BaseCommand):
    @property
    def name(self) -> str:
        return "/tools"
        
    @property
    def description(self) -> str:
        return "List all available tools and their descriptions"
        
    def execute(self, args: str, session: SessionContext) -> bool:
        tools_info = ""
        for tool in tools_schema:
            func = tool.get('function', {})
            name = func.get('name', 'Unknown')
            desc = func.get('description', 'No description provided.')
            tools_info += f"• {name}: {desc}\n"

        draw_box(tools_info.strip(), title="Available Tools", width=80, color_code="35")
        return True
