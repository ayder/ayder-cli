"""Additional tests for ui.py to reach 95%+ coverage.

This module tests the remaining uncovered lines in ui.py:
- Line 75: print_tool_skipped()
- Lines 105-110: search_codebase in describe_tool_action()
- Lines 223-224: Exception handling in generate_diff_preview()
- Line 238: Warning in confirm_with_diff()
"""

from unittest.mock import patch, MagicMock

from ayder_cli import ui


class TestPrintToolSkipped:
    """Tests for print_tool_skipped() function - Line 75."""

    @patch("ayder_cli.ui.console.print")
    def test_print_tool_skipped(self, mock_print):
        """Test tool skipped indicator printing."""
        ui.print_tool_skipped()
        mock_print.assert_called_once()
        call_args = mock_print.call_args[0][0]
        assert "✗" in str(call_args)
        assert "Tool call skipped by user" in str(call_args)


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
    @patch("ayder_cli.ui.console.print")
    def test_confirm_with_diff_none_shows_warning(self, mock_print, mock_confirm, mock_gen_diff):
        """Test that warning is shown when diff is None."""
        mock_gen_diff.return_value = None
        mock_confirm.return_value = True

        result = ui.confirm_with_diff("/path/to/file", "new content", "Test description")

        # Check that warning was printed via console.print
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
    @patch("ayder_cli.ui.console.print")
    def test_confirm_with_diff_binary_file_warning(self, mock_print, mock_confirm, mock_gen_diff):
        """Test warning for binary file (diff returns None)."""
        mock_gen_diff.return_value = None
        mock_confirm.return_value = False

        result = ui.confirm_with_diff("/path/to/binary", b"\x00\x01\x02", "Binary file")

        # Check that warning was printed via console.print
        warning_printed = False
        for call in mock_print.call_args_list:
            args = call[0][0] if call[0] else ""
            if "Warning" in str(args):
                warning_printed = True
                break
        
        assert warning_printed
        assert result is False


class TestColorizeDiffEdgeCases:
    """Additional edge case tests for colorize_diff()."""

    def test_colorize_diff_empty_lines(self):
        """Test colorize_diff with empty lines list."""
        result = ui.colorize_diff([])
        assert result == []

    def test_colorize_diff_context_lines(self):
        """Test that context lines (no special prefix) are not colorized."""
        from rich.text import Text
        lines = [" context line", " another context"]
        result = ui.colorize_diff(lines)
        # Result is now a list of Rich Text objects with plain content preserved
        assert isinstance(result[0], Text)
        assert isinstance(result[1], Text)
        assert result[0].plain == " context line"
        assert result[1].plain == " another context"

    def test_colorize_diff_mixed_lines(self):
        """Test colorize_diff with mixed line types."""
        from rich.text import Text
        lines = [
            "@@ -1,5 +1,5 @@",
            "--- a/file.txt",
            "+++ b/file.txt",
            "-removed line",
            "+added line",
            " context line"
        ]
        result = ui.colorize_diff(lines)
        
        # Result is a list of Rich Text objects
        # Check hunk header is cyan (Text with cyan style applied via spans)
        assert isinstance(result[0], Text)
        assert result[0].plain == "@@ -1,5 +1,5 @@"
        # Check that hunk header has a cyan span
        has_cyan = any("cyan" in str(span.style).lower() for span in result[0].spans)
        assert has_cyan, "Hunk header should have cyan style"
        
        # Check --- line is NOT colored (excluded) - should be plain Text
        assert isinstance(result[1], Text)
        assert result[1].plain == "--- a/file.txt"
        
        # Check +++ line is NOT colored (excluded) - should be plain Text  
        assert isinstance(result[2], Text)
        assert result[2].plain == "+++ b/file.txt"
        
        # Check - line is red
        assert isinstance(result[3], Text)
        assert result[3].plain == "-removed line"
        has_red = any("red" in str(span.style).lower() for span in result[3].spans)
        assert has_red, "Removal line should have red style"
        
        # Check + line is green
        assert isinstance(result[4], Text)
        assert result[4].plain == "+added line"
        has_green = any("green" in str(span.style).lower() for span in result[4].spans)
        assert has_green, "Addition line should have green style"
        
        # Check context line is unchanged - should be plain Text with original content
        assert isinstance(result[5], Text)
        assert result[5].plain == " context line"


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


# =============================================================================
# New tests for uncovered lines in ui.py
# =============================================================================

class TestPrintUserMessage:
    """Tests for print_user_message() function."""

    @patch("ayder_cli.ui.console.print")
    def test_prints_panel_with_you_title(self, mock_print):
        """Verify panel with 'You' title is printed."""
        from rich.panel import Panel
        ui.print_user_message("hello")
        mock_print.assert_called_once()
        panel = mock_print.call_args[0][0]
        assert isinstance(panel, Panel)
        assert panel.title == "You"


class TestPrintAssistantMessage:
    """Tests for print_assistant_message() function."""

    @patch("ayder_cli.ui.console.print")
    def test_prints_panel_with_assistant_title(self, mock_print):
        """Verify panel with 'Assistant' title is printed."""
        from rich.panel import Panel
        ui.print_assistant_message("response")
        mock_print.assert_called_once()
        panel = mock_print.call_args[0][0]
        assert isinstance(panel, Panel)
        assert panel.title == "Assistant"


class TestPrintToolCall:
    """Tests for print_tool_call() function."""

    @patch("ayder_cli.ui.console.print")
    def test_prints_tool_call_panel(self, mock_print):
        """Verify tool call panel is printed."""
        from rich.panel import Panel
        ui.print_tool_call("read_file", '{"file_path": "test.py"}')
        mock_print.assert_called_once()
        panel = mock_print.call_args[0][0]
        assert isinstance(panel, Panel)
        assert panel.title == "Tool Call"


class TestPrintFileContentRich:
    """Tests for print_file_content_rich() function."""

    @patch("ayder_cli.ui.console.print")
    def test_with_content_param(self, mock_print):
        """Test with content parameter."""
        ui.print_file_content_rich("test.py", content="print('hi')")
        mock_print.assert_called_once()

    @patch("ayder_cli.ui.console.print")
    @patch("builtins.open", side_effect=FileNotFoundError("not found"))
    def test_file_read_error(self, mock_open, mock_print):
        """Test file read error handling."""
        from rich.panel import Panel
        ui.print_file_content_rich("nonexistent.py")
        mock_print.assert_called_once()
        panel = mock_print.call_args[0][0]
        assert isinstance(panel, Panel)
        assert panel.title == "Error"


class TestPrintMarkdown:
    """Tests for print_markdown() function."""

    @patch("ayder_cli.ui.console.print")
    def test_without_title(self, mock_print):
        """Test without title parameter."""
        ui.print_markdown("# Hello")
        mock_print.assert_called_once()

    @patch("ayder_cli.ui.console.print")
    def test_with_title(self, mock_print):
        """Test with title parameter."""
        from rich.panel import Panel
        ui.print_markdown("# Hello", title="Docs")
        mock_print.assert_called_once()
        panel = mock_print.call_args[0][0]
        assert isinstance(panel, Panel)


class TestPrintCodeBlock:
    """Tests for print_code_block() function."""

    @patch("ayder_cli.ui.console.print")
    def test_basic_code_block(self, mock_print):
        """Test basic code block printing."""
        ui.print_code_block("x = 1", language="python")
        mock_print.assert_called_once()

    @patch("ayder_cli.ui.console.print")
    def test_code_block_with_title(self, mock_print):
        """Test code block with title."""
        ui.print_code_block("x = 1", title="Example")
        mock_print.assert_called_once()


class TestContextManagers:
    """Tests for context manager functions."""

    @patch("ayder_cli.ui.console.status")
    def test_agent_working_status(self, mock_status):
        """Test agent_working_status context manager."""
        with ui.agent_working_status("Processing..."):
            pass
        mock_status.assert_called_once()

    @patch("ayder_cli.ui.console.print")
    def test_print_running_rich(self, mock_print):
        """Test print_running_rich function."""
        ui.print_running_rich("Working...")
        mock_print.assert_called_once()

    @patch("ayder_cli.ui.console.status")
    def test_tool_execution_status(self, mock_status):
        """Test tool_execution_status context manager."""
        with ui.tool_execution_status("read_file"):
            pass
        mock_status.assert_called_once()

    @patch("ayder_cli.ui.console.status")
    def test_file_operation_status(self, mock_status):
        """Test file_operation_status context manager."""
        with ui.file_operation_status("reading", "test.py"):
            pass
        mock_status.assert_called_once()

    @patch("ayder_cli.ui.console.status")
    def test_file_operation_status_long_path(self, mock_status):
        """Paths > 40 chars are truncated with '...' prefix."""
        long_path = "/very/long/path/that/exceeds/forty/characters/file.txt"
        with ui.file_operation_status("reading", long_path):
            pass
        mock_status.assert_called_once()
        call_args_str = str(mock_status.call_args)
        assert "..." in call_args_str

    @patch("ayder_cli.ui.console.status")
    def test_search_status(self, mock_status):
        """Test search_status context manager."""
        with ui.search_status("pattern"):
            pass
        mock_status.assert_called_once()

    @patch("ayder_cli.ui.console.status")
    def test_search_status_long_pattern(self, mock_status):
        """Patterns > 30 chars are truncated."""
        long_pattern = "a" * 40
        with ui.search_status(long_pattern):
            pass
        mock_status.assert_called_once()
        call_args_str = str(mock_status.call_args)
        assert "..." in call_args_str


class TestConfirmWithDiff:
    """Tests for confirm_with_diff() function."""

    @patch("ayder_cli.ui.console.print")
    @patch("ayder_cli.ui.confirm_tool_call")
    @patch("ayder_cli.ui.generate_diff_preview")
    def test_confirm_with_diff_available(self, mock_gen_diff, mock_confirm, mock_print):
        """Test when diff is available."""
        from rich.text import Text
        mock_diff = Text("diff content")
        mock_gen_diff.return_value = mock_diff
        mock_confirm.return_value = True

        result = ui.confirm_with_diff("/path/to/file", "new content", "Test description")

        # Should print the diff panel
        mock_print.assert_called_once()
        assert result is True
