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


def run_tui(
    model: str = "default",
    safe_mode: bool = False,
    permissions: set = None,
    iterations: int = None,
) -> None:
    """
    Run the CLI-style TUI application.

    Args:
        model: The LLM model name to use
        safe_mode: Whether to enable safe mode
        permissions: Set of granted permission levels ("r", "w", "x")
        iterations: Max agentic iterations per message (None = use config default)
    """
    import sys

    app = AyderApp(
        model=model, safe_mode=safe_mode, permissions=permissions, iterations=iterations
    )
    app.run(mouse=False)

    # Ensure mouse reporting is disabled after exit — Textual's driver may
    # leave it on if the shutdown path doesn't fully complete (e.g. Ctrl+Q).
    sys.stdout.write(
        "\033[?1000l"  # disable mouse click tracking
        "\033[?1002l"  # disable mouse button-event tracking
        "\033[?1003l"  # disable all mouse tracking
        "\033[?1006l"  # disable SGR extended mouse mode
    )
    sys.stdout.flush()


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
