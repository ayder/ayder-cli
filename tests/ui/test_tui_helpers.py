"""Tests for tui_helpers — is_tool_blocked_in_safe_mode.

Note: Tests the actual implementation in ayder_cli.tui.helpers.
The tui_helpers.py shim is deprecated and will be removed.
"""
import pytest
from ayder_cli.tui.helpers import is_tool_blocked_in_safe_mode


class TestIsToolBlockedInSafeMode:
    """Tests for is_tool_blocked_in_safe_mode function."""

    def test_safe_mode_disabled_returns_false(self):
        """When safe_mode=False, no tool is blocked."""
        assert is_tool_blocked_in_safe_mode("write_file", False) is False
        assert is_tool_blocked_in_safe_mode("run_shell_command", False) is False
        assert is_tool_blocked_in_safe_mode("read_file", False) is False

    def test_write_file_blocked_in_safe_mode(self):
        """write_file should be blocked in safe mode."""
        assert is_tool_blocked_in_safe_mode("write_file", True) is True

    def test_replace_string_blocked_in_safe_mode(self):
        """replace_string should be blocked in safe mode."""
        assert is_tool_blocked_in_safe_mode("replace_string", True) is True

    def test_run_shell_command_blocked_in_safe_mode(self):
        """run_shell_command should be blocked in safe mode."""
        assert is_tool_blocked_in_safe_mode("run_shell_command", True) is True

    def test_read_file_not_blocked_in_safe_mode(self):
        """read_file should not be blocked in safe mode."""
        assert is_tool_blocked_in_safe_mode("read_file", True) is False

    def test_list_files_not_blocked_in_safe_mode(self):
        """list_files should not be blocked in safe mode."""
        assert is_tool_blocked_in_safe_mode("list_files", True) is False

    def test_search_codebase_not_blocked_in_safe_mode(self):
        """search_codebase should not be blocked in safe mode."""
        assert is_tool_blocked_in_safe_mode("search_codebase", True) is False

    def test_unknown_tool_not_blocked(self):
        """Unknown tool name returns False (tool_def is None)."""
        assert is_tool_blocked_in_safe_mode("nonexistent_tool", True) is False
        assert is_tool_blocked_in_safe_mode("nonexistent_tool", False) is False
