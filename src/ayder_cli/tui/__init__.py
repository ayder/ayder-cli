"""
CLI-style TUI (Terminal User Interface) for ayder-cli.

Provides a clean, terminal-like interface:
- Simple text output with prefixes (> for user, < for assistant)
- Minimal borders and chrome
- Slash command auto-completion
- Status bar with context info
"""

from ayder_cli.tui.types import MessageType, ConfirmResult
from ayder_cli.tui.screens import (
    CLIConfirmScreen,
    CLIPermissionScreen,
    CLISafeModeScreen,
    CLISelectScreen,
    TaskEditScreen,
)
from ayder_cli.tui.widgets import (
    ChatView,
    ToolPanel,
    AutoCompleteInput,
    CLIInputBar,
    StatusBar,
)
from ayder_cli.tui.app import AyderApp


def run_tui(model: str = "default", safe_mode: bool = False, permissions: set = None) -> None:
    """
    Run the CLI-style TUI application.

    Args:
        model: The LLM model name to use
        safe_mode: Whether to enable safe mode
        permissions: Set of granted permission levels ("r", "w", "x")
    """
    app = AyderApp(model=model, safe_mode=safe_mode, permissions=permissions)
    app.run(inline=True, inline_no_clear=True, mouse=False)


__all__ = [
    "MessageType",
    "ConfirmResult",
    "CLIConfirmScreen",
    "CLIPermissionScreen",
    "CLISafeModeScreen",
    "CLISelectScreen",
    "TaskEditScreen",
    "ChatView",
    "ToolPanel",
    "AutoCompleteInput",
    "CLIInputBar",
    "StatusBar",
    "AyderApp",
    "run_tui",
]
