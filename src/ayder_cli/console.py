"""
Centralized console instance for Rich UI.

This module provides a global Console instance that should be used
across the application for consistent styling and output.
"""

from rich.console import Console
from rich.theme import Theme

# Custom theme for ayder-cli
CUSTOM_THEME = Theme(
    {
        "info": "cyan",
        "success": "green",
        "warning": "yellow",
        "error": "bold red",
        "tool_call": "yellow",
        "user": "cyan",
        "assistant": "green",
        "border": "bright_black",
    }
)

# Global console instance
console = Console(theme=CUSTOM_THEME)
