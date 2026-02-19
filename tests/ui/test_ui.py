"""Tests for ui.py module."""

from unittest.mock import patch


from ayder_cli import ui


class TestPrintUserMessage:
    """Tests for print_user_message() function."""

    @patch("ayder_cli.ui.console.print")
    def test_print_user_message(self, mock_print):
        """Test user message printing."""
        from rich.panel import Panel
        ui.print_user_message("Hello user")
        mock_print.assert_called_once()
        panel = mock_print.call_args[0][0]
        assert isinstance(panel, Panel)
        assert panel.title == "You"


class TestPrintAssistantMessage:
    """Tests for print_assistant_message() function."""

    @patch("ayder_cli.ui.console.print")
    def test_print_assistant_message(self, mock_print):
        """Test assistant message printing."""
        from rich.panel import Panel
        ui.print_assistant_message("Hello from assistant")
        mock_print.assert_called_once()
        panel = mock_print.call_args[0][0]
        assert isinstance(panel, Panel)
        assert panel.title == "Assistant"


class TestPrintToolCall:
    """Tests for print_tool_call() function."""

    @patch("ayder_cli.ui.console.print")
    def test_print_tool_call(self, mock_print):
        """Test tool call printing."""
        from rich.panel import Panel
        ui.print_tool_call("my_function", '{"arg": "value"}')
        mock_print.assert_called_once()
        panel = mock_print.call_args[0][0]
        assert isinstance(panel, Panel)
        assert panel.title == "Tool Call"


class TestPrintToolResult:
    """Tests for print_tool_result() function."""

    @patch("ayder_cli.ui.console.print")
    def test_print_tool_result(self, mock_print):
        """Test tool result printing."""
        ui.print_tool_result("Success result")
        mock_print.assert_called_once()
        call_args = mock_print.call_args[0][0]
        assert "✓" in call_args
        assert "Success result" in call_args

    @patch("ayder_cli.ui.console.print")
    def test_truncation_over_300_chars(self, mock_print):
        """Test that results over 300 chars are truncated."""
        long_result = "A" * 400
        ui.print_tool_result(long_result)
        mock_print.assert_called_once()
        call_args = mock_print.call_args[0][0]
        assert "✓" in call_args
        assert "..." in call_args
        # Should be truncated to 300 chars (300 + "...")
        assert len([c for c in call_args if c == "A"]) <= 300


class TestPrintRunning:
    """Tests for print_running() function."""

    @patch("ayder_cli.ui.console.print")
    def test_print_running(self, mock_print):
        """Test running indicator printing."""
        ui.print_running()
        mock_print.assert_called_once()
        call_args = mock_print.call_args[0][0]
        assert "Running..." in call_args
        assert "\n" in call_args  # Has leading newline


class TestDescribeToolAction:
    """Tests for describe_tool_action() function."""

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

    def test_unknown_tool(self):
        """Test description for unknown tool."""
        result = ui.describe_tool_action("unknown_tool", {"arg": "value"})
        assert "unknown_tool" in result
        assert "will be called" in result

    def test_with_string_args(self):
        """Test with JSON string arguments."""
        args_json = '{"file_path": "/tmp/test.txt", "content": "hello"}'
        result = ui.describe_tool_action("write_file", args_json)
        assert "/tmp/test.txt" in result

    def test_with_dict_args(self):
        """Test with dict arguments directly."""
        args_dict = {"file_path": "/path/to/file"}
        result = ui.describe_tool_action("write_file", args_dict)
        assert "/path/to/file" in result

    def test_with_invalid_json_string(self):
        """Test with invalid JSON string."""
        result = ui.describe_tool_action("write_file", "not valid json")
        # Should fallback to empty args and use default template
        assert "will be written" in result

    def test_missing_required_args(self):
        """Test with missing required arguments."""
        result = ui.describe_tool_action("write_file", {})
        assert "unknown" in result


class TestPrintFileContent:
    """Tests for print_file_content() function."""

    @patch("ayder_cli.ui.console.print")
    def test_print_file_content_success(self, mock_print, tmp_path):
        """Test printing file content successfully."""
        from rich.panel import Panel
        test_file = tmp_path / "test.txt"
        test_file.write_text("File content here")
        ui.print_file_content(str(test_file))
        mock_print.assert_called_once()
        panel = mock_print.call_args[0][0]
        assert isinstance(panel, Panel)

    @patch("ayder_cli.ui.console.print")
    def test_print_file_content_error(self, mock_print):
        """Test error handling for non-existent file."""
        from rich.panel import Panel
        ui.print_file_content("/nonexistent/file.txt")
        mock_print.assert_called_once()
        panel = mock_print.call_args[0][0]
        assert isinstance(panel, Panel)
        assert panel.title == "Verbose Error"


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
    @patch("ayder_cli.ui.console.print")
    def test_keyboard_interrupt_returns_false(self, mock_print, mock_input):
        """Test KeyboardInterrupt returns False."""
        result = ui.confirm_tool_call("Do something")
        assert result is False
        # console.print is called twice: once for prompt, once for newline on interrupt
        assert mock_print.call_count == 2

    @patch("builtins.input", side_effect=EOFError)
    @patch("ayder_cli.ui.console.print")
    def test_eof_error_returns_false(self, mock_print, mock_input):
        """Test EOFError returns False."""
        result = ui.confirm_tool_call("Do something")
        assert result is False
        # console.print is called twice: once for prompt, once for newline on EOFError
        assert mock_print.call_count == 2

    @patch("builtins.input", return_value="y")
    @patch("ayder_cli.ui.console.print")
    def test_with_description(self, mock_print, mock_input):
        """Test that description is included in prompt."""
        ui.confirm_tool_call("Create file")
        # Description is now printed via console.print, not passed to input()
        # Check that console.print was called with the description
        mock_print.assert_called_once()
        call_args = mock_print.call_args[0][0]
        assert "Create file" in str(call_args)
        # input() is called with no args now
        mock_input.assert_called_once_with()

    @patch("builtins.input", return_value="y")
    @patch("ayder_cli.ui.console.print")
    def test_without_description(self, mock_print, mock_input):
        """Test that prompt works without description."""
        ui.confirm_tool_call()
        # Check that console.print was called with "Proceed?"
        mock_print.assert_called_once()
        call_args = mock_print.call_args[0][0]
        assert "Proceed?" in str(call_args)
        # input() is called with no args now
        mock_input.assert_called_once_with()

    @patch("builtins.input", return_value="maybe")
    @patch("builtins.print")
    def test_other_response_returns_false(self, mock_print, mock_input):
        """Test that any other response returns False."""
        result = ui.confirm_tool_call("Do something")
        assert result is False

