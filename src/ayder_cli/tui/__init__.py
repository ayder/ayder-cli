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
    CLIHelpScreen,
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
    permissions: set | None = None,
    agent_mode: bool = False,
    system_prompt_override: str | None = None,
) -> None:
    """
    Run the CLI-style TUI application.

    Args:
        model: The LLM model name to use
        safe_mode: Whether to enable safe mode
        permissions: Set of granted permission levels ("r", "w", "x")
        agent_mode: When True, inject the AGENTIC orchestrator system prompt
            so the main LLM drives the multi-agent harness (ayder-cli --agent).
        system_prompt_override: When set, use this text as the system-prompt base
            instead of the built-in prompts.py prompt (ayder --system-prompt FILE).
    """
    import sys
    from ayder_cli.providers import ProviderUnavailableError

    try:
        app = AyderApp(
            model=model, safe_mode=safe_mode, permissions=permissions,
            agent_mode=agent_mode, system_prompt_override=system_prompt_override,
        )
    except ProviderUnavailableError as e:
        print(str(e), file=sys.stderr)
        raise SystemExit(1)

    app.run(inline=True, mouse=False)

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
    "CLIHelpScreen",
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
