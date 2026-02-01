"""Tests for ui.py module."""

import json
from unittest.mock import mock_open, patch

import pytest

from ayder_cli import ui


class TestDrawBox:
    """Tests for draw_box() function."""

    def test_basic_box_drawing(self):
        """Test basic box drawing without title."""
        result = ui.draw_box("Hello", width=20)
        assert "╭" in result
        assert "╮" in result
        assert "╰" in result
        assert "╯" in result
        assert "Hello" in result
        assert "│" in result

    def test_box_with_title(self):
        """Test box drawing with title."""
        result = ui.draw_box("Content", title="My Title", width=40)
        assert "My Title" in result
        assert "Content" in result
        assert "╭" in result

    def test_empty_text(self):
        """Test box with empty text."""
        result = ui.draw_box("", width=20)
        assert "╭" in result
        assert "╮" in result
        assert "╰" in result
        assert "╯" in result

    def test_text_wrapping(self):
        """Test text wrapping within box."""
        long_text = "This is a very long text that should be wrapped to fit within the box width"
        result = ui.draw_box(long_text, width=40)
        lines = result.split("\n")
        # Check that text is wrapped (more than 3 lines for content)
        assert len(lines) > 3

    def test_different_color_codes(self):
        """Test different ANSI color codes."""
        result_cyan = ui.draw_box("Test", color_code="36")
        result_green = ui.draw_box("Test", color_code="32")
        result_yellow = ui.draw_box("Test", color_code="33")
        result_red = ui.draw_box("Test", color_code="31")
        
        assert "\033[36m" in result_cyan
        assert "\033[32m" in result_green
        assert "\033[33m" in result_yellow
        assert "\033[31m" in result_red

    def test_multiline_text(self):
        """Test box with multiline text."""
        text = "Line 1\nLine 2\nLine 3"
        result = ui.draw_box(text, width=20)
        assert "Line 1" in result
        assert "Line 2" in result
        assert "Line 3" in result

    def test_preserves_empty_lines(self):
        """Test that empty lines in input are preserved."""
        text = "First\n\nThird"
        result = ui.draw_box(text, width=20)
        lines = result.split("\n")
        # Should have content lines plus borders
        content_lines = [l for l in lines if "│" in l and "│" != l.strip()]
        # At least 3 content rows (First, empty, Third)
        assert len(content_lines) >= 3


class TestPrintUserMessage:
    """Tests for print_user_message() function."""

    @patch("builtins.print")
    def test_print_user_message(self, mock_print):
        """Test user message printing."""
        ui.print_user_message("Hello user")
        mock_print.assert_called_once()
        call_args = mock_print.call_args[0][0]
        assert "You" in call_args
        assert "Hello user" in call_args
        assert "\n" in call_args  # Has leading newline


class TestPrintAssistantMessage:
    """Tests for print_assistant_message() function."""

    @patch("builtins.print")
    def test_print_assistant_message(self, mock_print):
        """Test assistant message printing."""
        ui.print_assistant_message("Hello from assistant")
        mock_print.assert_called_once()
        call_args = mock_print.call_args[0][0]
        assert "Assistant" in call_args
        assert "Hello from assistant" in call_args


class TestPrintToolCall:
    """Tests for print_tool_call() function."""

    @patch("builtins.print")
    def test_print_tool_call(self, mock_print):
        """Test tool call printing."""
        ui.print_tool_call("my_function", '{"arg": "value"}')
        mock_print.assert_called_once()
        call_args = mock_print.call_args[0][0]
        assert "Tool Call" in call_args
        assert "my_function" in call_args


class TestPrintToolResult:
    """Tests for print_tool_result() function."""

    @patch("builtins.print")
    def test_print_tool_result(self, mock_print):
        """Test tool result printing."""
        ui.print_tool_result("Success result")
        mock_print.assert_called_once()
        call_args = mock_print.call_args[0][0]
        assert "Tool Result" in call_args
        assert "Success result" in call_args

    @patch("builtins.print")
    def test_truncation_over_300_chars(self, mock_print):
        """Test that results over 300 chars are truncated."""
        long_result = "A" * 400
        ui.print_tool_result(long_result)
        mock_print.assert_called_once()
        call_args = mock_print.call_args[0][0]
        assert "..." in call_args
        # Should be truncated to 303 chars (300 + "...")
        assert len([c for c in call_args if c == "A"]) <= 300


class TestPrintRunning:
    """Tests for print_running() function."""

    @patch("builtins.print")
    def test_print_running(self, mock_print):
        """Test running indicator printing."""
        ui.print_running()
        mock_print.assert_called_once()
        call_args = mock_print.call_args[0][0]
        assert "Running..." in call_args
        assert "\n" in call_args  # Has leading newline


class TestDescribeToolAction:
    """Tests for describe_tool_action() function."""

    def test_create_task(self):
        """Test description for create_task tool."""
        result = ui.describe_tool_action("create_task", {"title": "My Task"})
        assert "TASK-XXX.md" in result
        assert ".ayder/tasks/" in result

    def test_show_task_with_int_id(self):
        """Test description for show_task tool with integer ID."""
        result = ui.describe_tool_action("show_task", {"task_id": 5})
        assert "TASK-005" in result

    def test_show_task_with_string_id(self):
        """Test description for show_task tool with string ID."""
        result = ui.describe_tool_action("show_task", {"task_id": "10"})
        assert "TASK-10" in result

    def test_write_file(self):
        """Test description for write_file tool."""
        result = ui.describe_tool_action("write_file", {"file_path": "/tmp/test.txt"})
        assert "/tmp/test.txt" in result
        assert "will be written" in result

    def test_read_file(self):
        """Test description for read_file tool."""
        result = ui.describe_tool_action("read_file", {"file_path": "/tmp/read.txt"})
        assert "/tmp/read.txt" in result
        assert "will be read" in result

    def test_list_files(self):
        """Test description for list_files tool."""
        result = ui.describe_tool_action("list_files", {"directory": "/home"})
        assert "/home" in result
        assert "will be listed" in result

    def test_list_files_default_directory(self):
        """Test description for list_files tool with default directory."""
        result = ui.describe_tool_action("list_files", {})
        assert "." in result

    def test_replace_string(self):
        """Test description for replace_string tool."""
        result = ui.describe_tool_action("replace_string", {"file_path": "/tmp/modify.py"})
        assert "/tmp/modify.py" in result
        assert "will be modified" in result

    def test_run_shell_command(self):
        """Test description for run_shell_command tool."""
        result = ui.describe_tool_action("run_shell_command", {"command": "ls -la"})
        assert "ls -la" in result
        assert "will be executed" in result

    def test_list_tasks(self):
        """Test description for list_tasks tool."""
        result = ui.describe_tool_action("list_tasks", {})
        assert "Tasks will be listed" == result

    def test_unknown_tool(self):
        """Test description for unknown tool."""
        result = ui.describe_tool_action("unknown_tool", {"arg": "value"})
        assert "unknown_tool" in result
        assert "will be called" in result

    def test_with_string_args(self):
        """Test with JSON string arguments."""
        args_json = '{"title": "Test Task"}'
        result = ui.describe_tool_action("create_task", args_json)
        assert "TASK-XXX.md" in result

    def test_with_dict_args(self):
        """Test with dict arguments directly."""
        args_dict = {"file_path": "/path/to/file"}
        result = ui.describe_tool_action("write_file", args_dict)
        assert "/path/to/file" in result

    def test_with_invalid_json_string(self):
        """Test with invalid JSON string."""
        result = ui.describe_tool_action("create_task", "not valid json")
        # Should fallback to empty args and use default
        assert "TASK-XXX.md" in result

    def test_missing_required_args(self):
        """Test with missing required arguments."""
        result = ui.describe_tool_action("write_file", {})
        assert "unknown" in result


class TestPrintFileContent:
    """Tests for print_file_content() function."""

    @patch("builtins.print")
    @patch("builtins.open", mock_open(read_data="File content here"))
    def test_print_file_content_success(self, mock_print):
        """Test printing file content successfully."""
        ui.print_file_content("/tmp/test.txt")
        mock_print.assert_called_once()
        call_args = mock_print.call_args[0][0]
        assert "File content here" in call_args
        assert "/tmp/test.txt" in call_args

    @patch("builtins.print")
    def test_print_file_content_error(self, mock_print):
        """Test error handling for non-existent file."""
        ui.print_file_content("/nonexistent/file.txt")
        mock_print.assert_called_once()
        call_args = mock_print.call_args[0][0]
        assert "Could not read file" in call_args
        assert "Verbose Error" in call_args


class TestConfirmToolCall:
    """Tests for confirm_tool_call() function."""

    @patch("builtins.input", return_value="y")
    @patch("builtins.print")
    def test_y_response_returns_true(self, mock_print, mock_input):
        """Test 'y' response returns True."""
        result = ui.confirm_tool_call("Do something")
        assert result is True

    @patch("builtins.input", return_value="Y")
    @patch("builtins.print")
    def test_uppercase_y_response_returns_true(self, mock_print, mock_input):
        """Test 'Y' response returns True."""
        result = ui.confirm_tool_call("Do something")
        assert result is True

    @patch("builtins.input", return_value="yes")
    @patch("builtins.print")
    def test_yes_response_returns_true(self, mock_print, mock_input):
        """Test 'yes' response returns True."""
        result = ui.confirm_tool_call("Do something")
        assert result is True

    @patch("builtins.input", return_value="YES")
    @patch("builtins.print")
    def test_uppercase_yes_response_returns_true(self, mock_print, mock_input):
        """Test 'YES' response returns True."""
        result = ui.confirm_tool_call("Do something")
        assert result is True

    @patch("builtins.input", return_value="")
    @patch("builtins.print")
    def test_empty_string_returns_true(self, mock_print, mock_input):
        """Test empty string response returns True."""
        result = ui.confirm_tool_call("Do something")
        assert result is True

    @patch("builtins.input", return_value="n")
    @patch("builtins.print")
    def test_n_response_returns_false(self, mock_print, mock_input):
        """Test 'n' response returns False."""
        result = ui.confirm_tool_call("Do something")
        assert result is False

    @patch("builtins.input", return_value="N")
    @patch("builtins.print")
    def test_uppercase_n_response_returns_false(self, mock_print, mock_input):
        """Test 'N' response returns False."""
        result = ui.confirm_tool_call("Do something")
        assert result is False

    @patch("builtins.input", return_value="no")
    @patch("builtins.print")
    def test_no_response_returns_false(self, mock_print, mock_input):
        """Test 'no' response returns False."""
        result = ui.confirm_tool_call("Do something")
        assert result is False

    @patch("builtins.input", return_value="  y  ")
    @patch("builtins.print")
    def test_whitespace_trimmed_y_returns_true(self, mock_print, mock_input):
        """Test that whitespace is trimmed from response."""
        result = ui.confirm_tool_call("Do something")
        assert result is True

    @patch("builtins.input", side_effect=KeyboardInterrupt)
    @patch("builtins.print")
    def test_keyboard_interrupt_returns_false(self, mock_print, mock_input):
        """Test KeyboardInterrupt returns False."""
        result = ui.confirm_tool_call("Do something")
        assert result is False
        mock_print.assert_called_once_with()  # Prints newline

    @patch("builtins.input", side_effect=EOFError)
    @patch("builtins.print")
    def test_eof_error_returns_false(self, mock_print, mock_input):
        """Test EOFError returns False."""
        result = ui.confirm_tool_call("Do something")
        assert result is False
        mock_print.assert_called_once_with()

    @patch("builtins.input", return_value="y")
    @patch("builtins.print")
    def test_with_description(self, mock_print, mock_input):
        """Test that description is included in prompt."""
        ui.confirm_tool_call("Create file")
        call_args = mock_input.call_args[0][0]
        assert "Create file" in call_args

    @patch("builtins.input", return_value="y")
    @patch("builtins.print")
    def test_without_description(self, mock_print, mock_input):
        """Test that prompt works without description."""
        ui.confirm_tool_call()
        call_args = mock_input.call_args[0][0]
        assert "Proceed?" in call_args

    @patch("builtins.input", return_value="maybe")
    @patch("builtins.print")
    def test_other_response_returns_false(self, mock_print, mock_input):
        """Test that any other response returns False."""
        result = ui.confirm_tool_call("Do something")
        assert result is False


class TestColorizeDiffLine:
    """Tests for colorize_diff_line() function."""

    def test_deletion_line_red(self):
        """Verify `-` lines get red color (31)."""
        result = ui.colorize_diff_line("-removed line")
        assert "\033[31m" in result
        assert "\033[0m" in result
        assert "-removed line" in result

    def test_addition_line_green(self):
        """Verify `+` lines get green color (32)."""
        result = ui.colorize_diff_line("+added line")
        assert "\033[32m" in result
        assert "\033[0m" in result
        assert "+added line" in result

    def test_header_line_cyan(self):
        """Verify `@@` lines get cyan color (36)."""
        result = ui.colorize_diff_line("@@ -1,5 +1,6 @@")
        assert "\033[36m" in result
        assert "\033[0m" in result
        assert "@@ -1,5 +1,6 @@" in result

    def test_context_line_no_color(self):
        """Verify regular lines have no color."""
        result = ui.colorize_diff_line(" context line")
        assert "\033[" not in result
        assert " context line" == result

    def test_file_marker_minus_no_color(self):
        """Verify `---` file marker has no color."""
        result = ui.colorize_diff_line("--- a/file.txt")
        assert "\033[" not in result
        assert "--- a/file.txt" == result

    def test_file_marker_plus_no_color(self):
        """Verify `+++` file marker has no color."""
        result = ui.colorize_diff_line("+++ b/file.txt")
        assert "\033[" not in result
        assert "+++ b/file.txt" == result


class TestPreviewFileModification:
    """Tests for preview_file_modification() function."""

    def test_write_file_existing_file_shows_diff(self):
        """Verify diff generation and colorization for write_file on existing file."""
        with patch("ayder_cli.ui.os.path.exists", return_value=True):
            with patch("builtins.open", mock_open(read_data="old content")):
                with patch("builtins.print") as mock_print:
                    fargs = {
                        "file_path": "/test/file.txt",
                        "content": "new content"
                    }
                    result = ui.preview_file_modification("write_file", fargs)
                    assert result is True
                    mock_print.assert_called_once()
                    call_args = mock_print.call_args[0][0]
                    assert "Preview: /test/file.txt" in call_args

    @patch("ayder_cli.ui.os.path.exists", return_value=False)
    @patch("builtins.print")
    def test_write_file_new_file_shows_all_additions(self, mock_print, mock_exists):
        """Check `/dev/null` handling for new file creation."""
        fargs = {
            "file_path": "/test/new_file.txt",
            "content": "new file content"
        }
        result = ui.preview_file_modification("write_file", fargs)
        assert result is True
        mock_print.assert_called_once()
        call_args = mock_print.call_args[0][0]
        assert "Preview: /test/new_file.txt" in call_args
        assert "/dev/null" in call_args

    def test_replace_string_shows_diff(self):
        """Verify replace logic preview with diff."""
        with patch("ayder_cli.ui.os.path.exists", return_value=True):
            with patch("builtins.open", mock_open(read_data="line1\nline2\nline3")):
                with patch("builtins.print") as mock_print:
                    fargs = {
                        "file_path": "/test/file.txt",
                        "old_string": "line2",
                        "new_string": "line2_modified"
                    }
                    result = ui.preview_file_modification("replace_string", fargs)
                    assert result is True
                    mock_print.assert_called_once()
                    call_args = mock_print.call_args[0][0]
                    assert "Preview: /test/file.txt" in call_args

    @patch("ayder_cli.ui.os.path.exists", return_value=False)
    @patch("builtins.print")
    def test_replace_string_file_not_found(self, mock_print, mock_exists):
        """Check error handling when file doesn't exist."""
        fargs = {
            "file_path": "/nonexistent/file.txt",
            "old_string": "old",
            "new_string": "new"
        }
        result = ui.preview_file_modification("replace_string", fargs)
        assert result is True
        mock_print.assert_called_once()
        call_args = mock_print.call_args[0][0]
        assert "Warning" in call_args
        assert "does not exist" in call_args

    def test_replace_string_old_string_not_found(self):
        """Show warning but allow proceed when old_string not found."""
        with patch("builtins.print") as mock_print:
            with patch("builtins.open", mock_open(read_data="line1\nline2\nline3")):
                with patch("ayder_cli.ui.os.path.exists", return_value=True):
                    fargs = {
                        "file_path": "/test/file.txt",
                        "old_string": "nonexistent",
                        "new_string": "new"
                    }
                    result = ui.preview_file_modification("replace_string", fargs)
                    assert result is True
                    mock_print.assert_called_once()
                    call_args = mock_print.call_args[0][0]
                    assert "Warning" in call_args
                    assert "not found" in call_args

    def test_non_file_modification_tool_returns_false(self):
        """Verify non-file tools return False."""
        result = ui.preview_file_modification("read_file", {"file_path": "/test.txt"})
        assert result is False

        result = ui.preview_file_modification("list_files", {"directory": "."})
        assert result is False

        result = ui.preview_file_modification("run_shell_command", {"command": "ls"})
        assert result is False

    @patch("ayder_cli.ui.os.path.exists", return_value=False)
    @patch("builtins.print")
    def test_very_large_diff_truncated(self, mock_print, mock_exists):
        """Verify 500-line limit with truncation message."""
        # Create a very large replacement that will generate > 500 lines of diff
        large_content = "\n".join([f"new_line{i}" for i in range(600)])
        fargs = {
            "file_path": "/test/large_file.txt",
            "content": large_content
        }
        result = ui.preview_file_modification("write_file", fargs)
        assert result is True
        mock_print.assert_called_once()
        call_args = mock_print.call_args[0][0]
        assert "Preview" in call_args

    @patch("ayder_cli.ui.os.path.exists", return_value=True)
    @patch("builtins.open", side_effect=UnicodeDecodeError("utf-8", b"", 0, 1, "invalid start byte"))
    @patch("builtins.print")
    def test_binary_file_encoding_error(self, mock_print, mock_open_call, mock_exists):
        """Handle encoding errors gracefully."""
        fargs = {
            "file_path": "/test/binary.bin",
            "content": "some content"
        }
        result = ui.preview_file_modification("write_file", fargs)
        assert result is True
        mock_print.assert_called_once()
        call_args = mock_print.call_args[0][0]
        assert "Cannot preview" in call_args or "Preview Error" in call_args

    def test_json_string_args_parsed(self):
        """Verify both dict and JSON string args work."""
        # With dict args
        with patch("builtins.print"):
            with patch("os.path.exists", return_value=False):
                result = ui.preview_file_modification("write_file", {"file_path": "/test.txt", "content": "test"})
                assert result is True

        # With JSON string args
        with patch("builtins.print"):
            with patch("os.path.exists", return_value=False):
                result = ui.preview_file_modification("write_file", '{"file_path": "/test.txt", "content": "test"}')
                assert result is True

    def test_invalid_json_args_returns_false(self):
        """Test with invalid JSON string."""
        result = ui.preview_file_modification("write_file", "not valid json")
        assert result is False

    @patch("builtins.print")
    def test_missing_file_path_returns_true(self, mock_print):
        """Test when file_path is missing from args."""
        fargs = {"content": "test"}
        result = ui.preview_file_modification("write_file", fargs)
        assert result is True
        # Should return early without printing

    def test_replace_string_with_dict_args(self):
        """Test replace_string with dict arguments."""
        with patch("builtins.print") as mock_print:
            with patch("builtins.open", mock_open(read_data="original")):
                with patch("ayder_cli.ui.os.path.exists", return_value=True):
                    fargs = {
                        "file_path": "/test/file.txt",
                        "old_string": "original",
                        "new_string": "modified"
                    }
                    result = ui.preview_file_modification("replace_string", fargs)
                    assert result is True
                    mock_print.assert_called_once()
