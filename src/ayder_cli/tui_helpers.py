"""
Helper functions for TUI operations like confirmations.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ayder_cli.tui import AyderApp


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
    
    blocked_tools = [
        "run_shell_command",
        "write_file",
        "replace_string",
    ]
    
    return tool_name in blocked_tools
