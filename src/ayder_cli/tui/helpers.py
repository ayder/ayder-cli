"""Helper functions for TUI operations like confirmations."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ayder_cli.tui.app import AyderApp


def is_tool_blocked_in_safe_mode(tool_name: str, safe_mode: bool) -> bool:
    """
    Check if a tool should be blocked in safe mode.

    Args:
        tool_name: Name of the tool
        safe_mode: Whether safe mode is enabled

    Returns:
        True if tool should be blocked
    """
    if not safe_mode:
        return False

    from ayder_cli.tools.definition import TOOL_DEFINITIONS_BY_NAME

    tool_def = TOOL_DEFINITIONS_BY_NAME.get(tool_name)
    return tool_def.safe_mode_blocked if tool_def else False
