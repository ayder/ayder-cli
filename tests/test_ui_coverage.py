"""Additional tests for ui.py to reach 95%+ coverage.

This module tests the remaining uncovered lines in ui.py:
- Line 75: print_tool_skipped()
- Lines 105-110: search_codebase in describe_tool_action()
- Lines 223-224: Exception handling in generate_diff_preview()
- Line 238: Warning in confirm_with_diff()
"""

import pytest
from unittest.mock import mock_open, patch, MagicMock
import pytest

from ayder_cli import ui


class TestPrintToolSkipped:
    """Tests for print_tool_skipped() function - Line 75."""

    @patch("builtins.print")
    def test_print_tool_skipped(self, mock_print):
        """Test tool skipped indicator printing."""
        ui.print_tool_skipped()
        mock_print.assert_called_once()
        call_args = mock_print.call_args[0][0]
        assert "✗" in call_args
        assert "Tool call skipped by user" in call_args
        assert "\n" in call_args  # Has leading newline


class TestDescribeToolActionSearchCodebase:
    """Tests for describe_tool_action() search_codebase - Lines 105-110."""

    def test_search_codebase_basic(self):
        """Test description for search_codebase with pattern only."""
        result = ui.describe_tool_action("search_codebase", {"pattern": "test_pattern"})
        assert "Codebase will be searched" in result
        assert "test_pattern" in result

    def test_search_codebase_with_file_pattern(self):
        """Test description for search_codebase with pattern and file_pattern."""
        result = ui.describe_tool_action("search_codebase", {
            "pattern": "foo",
            "file_pattern": "*.py"
        })
        assert "Codebase will be searched" in result
        assert "foo" in result
        assert "*.py" in result
        assert "in files matching" in result

    def test_search_codebase_default_pattern(self):
        """Test description for search_codebase with missing pattern."""
        result = ui.describe_tool_action("search_codebase", {})
        assert "Codebase will be searched" in result
        assert "unknown" in result

    def test_search_codebase_with_json_string(self):
        """Test search_codebase with JSON string arguments."""
        args_json = '{"pattern": "search_term", "file_pattern": "*.js"}'
        result = ui.describe_tool_action("search_codebase", args_json)
        assert "search_term" in result
        assert "*.js" in result


class TestGenerateDiffPreviewException:
    """Tests for generate_diff_preview() exception handling - Lines 223-224."""

    @patch("ayder_cli.ui.Path")
    def test_generate_diff_preview_exception(self, mock_path_class):
        """Test that exceptions in generate_diff_preview return None."""
        # Mock Path.exists to raise an exception
        mock_path = MagicMock()
        mock_path.exists.side_effect = Exception("Some error")
        mock_path_class.return_value = mock_path

        result = ui.generate_diff_preview("/some/path", "content")
        assert result is None

    @patch("ayder_cli.ui.Path")
    def test_generate_diff_preview_permission_error(self, mock_path_class):
        """Test that PermissionError in generate_diff_preview returns None."""
        mock_path = MagicMock()
        mock_path.exists.side_effect = PermissionError("Permission denied")
        mock_path_class.return_value = mock_path

        result = ui.generate_diff_preview("/restricted/path", "content")
        assert result is None


class TestConfirmWithDiffWarning:
    """Tests for confirm_with_diff() warning message - Line 238."""

    @patch("ayder_cli.ui.generate_diff_preview")
    @patch("ayder_cli.ui.confirm_tool_call")
    @patch("builtins.print")
    def test_confirm_with_diff_none_shows_warning(self, mock_print, mock_confirm, mock_gen_diff):
        """Test that warning is shown when diff is None."""
        mock_gen_diff.return_value = None
        mock_confirm.return_value = True

        result = ui.confirm_with_diff("/path/to/file", "new content", "Test description")

        # Check that warning was printed
        warning_printed = False
        for call in mock_print.call_args_list:
            args = call[0][0] if call[0] else ""
            if "Warning" in str(args) and "Unable to generate preview" in str(args):
                warning_printed = True
                break
        
        assert warning_printed, "Warning message should be printed when diff is None"
        assert result is True

    @patch("ayder_cli.ui.generate_diff_preview")
    @patch("ayder_cli.ui.confirm_tool_call")
    @patch("builtins.print")
    def test_confirm_with_diff_binary_file_warning(self, mock_print, mock_confirm, mock_gen_diff):
        """Test warning for binary file (diff returns None)."""
        mock_gen_diff.return_value = None
        mock_confirm.return_value = False

        result = ui.confirm_with_diff("/path/to/binary", b"\x00\x01\x02", "Binary file")

        # Check that warning was printed
        warning_printed = False
        for call in mock_print.call_args_list:
            args = call[0][0] if call[0] else ""
            if "Warning" in str(args):
                warning_printed = True
                break
        
        assert warning_printed
        assert result is False


@pytest.mark.skip(reason="TODO: Update for Rich UI")
class TestDrawBoxEdgeCases:
    """Additional edge case tests for draw_box()."""

    def test_draw_box_very_long_text(self):
        """Test draw_box with very long text that wraps extensively."""
        very_long_text = "word " * 200  # Very long text
        result = ui.draw_box(very_long_text, width=40)
        lines = result.split("\n")
        # Should have many wrapped lines
        assert len(lines) > 10
        # All lines should be within width
        for line in lines:
            # Exclude ANSI escape codes for length check
            clean_line = line.replace("\033[36m", "").replace("\033[0m", "")
            assert len(clean_line) <= 40 or "─" in clean_line

    def test_draw_box_narrow_width(self):
        """Test draw_box with narrow width."""
        text = "This is some text that needs wrapping"
        result = ui.draw_box(text, width=10)
        lines = result.split("\n")
        # Should wrap into multiple lines
        assert len(lines) > 3

    def test_draw_box_empty_lines_preserved(self):
        """Test that empty lines are preserved in output."""
        text = "Line1\n\n\nLine2"
        result = ui.draw_box(text, width=20)
        # Should preserve empty lines
        assert result.count("\n") >= 4


class TestColorizeDiffEdgeCases:
    """Additional edge case tests for colorize_diff()."""

    def test_colorize_diff_empty_lines(self):
        """Test colorize_diff with empty lines list."""
        result = ui.colorize_diff([])
        assert result == []

    def test_colorize_diff_context_lines(self):
        """Test that context lines (no special prefix) are not colorized."""
        lines = [" context line", " another context"]
        result = ui.colorize_diff(lines)
        assert result == lines  # Should be unchanged

    def test_colorize_diff_mixed_lines(self):
        """Test colorize_diff with mixed line types."""
        lines = [
            "@@ -1,5 +1,5 @@",
            "--- a/file.txt",
            "+++ b/file.txt",
            "-removed line",
            "+added line",
            " context line"
        ]
        result = ui.colorize_diff(lines)
        
        # Check hunk header is cyan
        assert "\033[36m" in result[0]
        # Check --- line is NOT colored (excluded)
        assert "\033[31m" not in result[1]
        # Check +++ line is NOT colored (excluded)
        assert "\033[32m" not in result[2]
        # Check - line is red
        assert "\033[31m" in result[3]
        # Check + line is green
        assert "\033[32m" in result[4]
        # Check context line is unchanged
        assert result[5] == " context line"


class TestTruncateDiffEdgeCases:
    """Additional edge case tests for truncate_diff()."""

    def test_truncate_diff_exactly_max_lines(self):
        """Test truncate_diff with exactly max_lines."""
        lines = [f"line{i}" for i in range(100)]
        result = ui.truncate_diff(lines, max_lines=100)
        assert result == lines

    def test_truncate_diff_one_over_max(self):
        """Test truncate_diff with one line over max."""
        lines = [f"line{i}" for i in range(101)]
        result = ui.truncate_diff(lines, max_lines=100)
        # Should truncate with separator (always returns 80 + 1 + 20 = 101 lines)
        assert any("omitted" in str(line) for line in result)
        # First 80 lines + separator + last 20 lines = 101 total
        assert len(result) == 101

    def test_truncate_diff_custom_max(self):
        """Test truncate_diff with custom max_lines value."""
        lines = [f"line{i}" for i in range(200)]
        result = ui.truncate_diff(lines, max_lines=100)
        # Should truncate since 200 > 100 (always returns 80 + 1 + 20 = 101 lines)
        assert any("omitted" in str(line) for line in result)
        # First 80 + separator + last 20 = 101 lines
        assert len(result) == 101
