"""Tests for ToolExecutor service."""

import pytest
from unittest.mock import Mock, patch, MagicMock

from ayder_cli.services.tools.executor import ToolExecutor, TERMINAL_TOOLS
from ayder_cli.client import ChatSession
from ayder_cli.core.config import Config
from ayder_cli.core.result import ToolSuccess

class TestToolExecutor:
    """Test ToolExecutor class."""

    def test_executor_initialization(self):
        """Test ToolExecutor initialization."""
        mock_registry = Mock()
        executor = ToolExecutor(mock_registry)
        assert executor.tool_registry == mock_registry
        assert executor.terminal_tools == TERMINAL_TOOLS

    def test_executor_initialization_custom_terminal_tools(self):
        """Test ToolExecutor initialization with custom terminal tools."""
        mock_registry = Mock()
        custom_terminal = {"stop"}
        executor = ToolExecutor(mock_registry, terminal_tools=custom_terminal)
        assert executor.terminal_tools == custom_terminal

    @patch("ayder_cli.services.tools.executor.confirm_tool_call")
    @patch("ayder_cli.services.tools.executor.describe_tool_action")
    @patch("ayder_cli.services.tools.executor.print_tool_result")
    def test_handle_tool_call(self, mock_print_result, mock_describe, mock_confirm):
        """Test handling a tool call."""
        mock_registry = Mock()
        executor = ToolExecutor(mock_registry)
        
        # Mock tool call
        mock_tool_call = Mock()
        mock_tool_call.id = "call_123"
        mock_tool_call.function.name = "list_files"
        mock_tool_call.function.arguments = '{"directory": "."}'
        
        # Mock registry
        mock_registry.normalize_args.return_value = {"directory": "."}
        mock_registry.validate_args.return_value = (True, None)
        mock_registry.execute.return_value = "file1.txt\nfile2.txt"
        
        mock_describe.return_value = "List files in ."
        mock_confirm.return_value = True
        
        result = executor._handle_tool_call(mock_tool_call, granted_permissions=set(), verbose=False)
        
        assert result is not None
        assert result["role"] == "tool"
        assert result["tool_call_id"] == "call_123"
        assert result["name"] == "list_files"
        assert "file1.txt" in result["content"]

    @patch("ayder_cli.services.tools.executor.print_tool_skipped")
    @patch("ayder_cli.services.tools.executor.describe_tool_action")
    @patch("ayder_cli.services.tools.executor.confirm_tool_call")
    def test_handle_tool_call_declined(self, mock_confirm, mock_describe, mock_skipped):
        """Test handling a declined tool call."""
        mock_registry = Mock()
        executor = ToolExecutor(mock_registry)
        
        # Mock tool call
        mock_tool_call = Mock()
        mock_tool_call.id = "call_123"
        mock_tool_call.function.name = "list_files"
        mock_tool_call.function.arguments = '{"directory": "."}'
        
        # Mock registry
        mock_registry.normalize_args.return_value = {"directory": "."}
        mock_registry.validate_args.return_value = (True, None)
        
        mock_describe.return_value = "List files in ."
        mock_confirm.return_value = False  # User declines
        
        result = executor._handle_tool_call(mock_tool_call, granted_permissions=set(), verbose=False)
        
        assert result is None
        mock_skipped.assert_called_once()

    def test_execute_tool_calls_with_declined_tool(self):
        """Test that declined tool stops the loop."""
        mock_registry = Mock()
        executor = ToolExecutor(mock_registry)
        session = Mock()
        session.messages = []
        
        # Mock a tool call
        mock_tool_call = Mock()
        
        with patch.object(executor, "_handle_tool_call", return_value=None):
            result = executor.execute_tool_calls([mock_tool_call], session)
        
        # Should return True when tool is declined
        assert result is True

    def test_execute_tool_calls_with_multiple_tools(self):
        """Test executing multiple tool calls."""
        mock_registry = Mock()
        executor = ToolExecutor(mock_registry)
        session = Mock()

        mock_tool_call1 = Mock()
        mock_tool_call1.function.name = "list_files"
        mock_tool_call2 = Mock()
        mock_tool_call2.function.name = "read_file"

        result_msg1 = {"role": "tool", "content": "files"}
        result_msg2 = {"role": "tool", "content": "content"}

        with patch.object(executor, "_handle_tool_call", side_effect=[result_msg1, result_msg2]):
            result = executor.execute_tool_calls([mock_tool_call1, mock_tool_call2], session)

        # Both tools executed, no terminal tool
        assert result is False
        # Both results should be appended via append_raw
        assert session.append_raw.call_count == 2
        session.append_raw.assert_any_call(result_msg1)
        session.append_raw.assert_any_call(result_msg2)

    @patch("ayder_cli.services.tools.executor.describe_tool_action")
    @patch("ayder_cli.services.tools.executor.print_tool_result")
    def test_handle_custom_calls_validation_error(self, mock_print_result, mock_describe):
        """Test validation error in custom calls stops execution."""
        mock_registry = Mock()
        executor = ToolExecutor(mock_registry)
        session = Mock()
        session.messages = []
        
        custom_calls = [{"name": "invalid_tool", "arguments": {}}]
        
        mock_registry.normalize_args.return_value = {}
        mock_registry.validate_args.return_value = (False, "Invalid tool")
        
        result = executor.execute_custom_calls(custom_calls, session)
        
        # Should return True on validation error
        assert result is True
        # Error message should be added to session (as call to add_message)
        session.add_message.assert_called_with("user", "Validation Error for tool 'invalid_tool': Invalid tool")

    @patch("ayder_cli.services.tools.executor.describe_tool_action")
    @patch("ayder_cli.services.tools.executor.print_tool_skipped")
    @patch("ayder_cli.services.tools.executor.confirm_tool_call")
    def test_handle_custom_calls_declined(self, mock_confirm, mock_print_skipped, mock_describe):
        """Test declined custom call stops execution."""
        mock_registry = Mock()
        executor = ToolExecutor(mock_registry)
        session = Mock()
        
        custom_calls = [{"name": "list_files", "arguments": {"directory": "."}}]
        
        mock_registry.normalize_args.return_value = {"directory": "."}
        mock_registry.validate_args.return_value = (True, None)
        mock_describe.return_value = "List files"
        mock_confirm.return_value = False
        
        result = executor.execute_custom_calls(custom_calls, session)
        
        # Should return True when declined
        assert result is True
        mock_print_skipped.assert_called_once()

    @patch("ayder_cli.services.tools.executor.describe_tool_action")
    @patch("ayder_cli.services.tools.executor.confirm_tool_call")
    @patch("ayder_cli.services.tools.executor.print_tool_result")
    def test_handle_custom_calls_with_terminal_tool(
        self, mock_print_result, mock_confirm, mock_describe
    ):
        """Test terminal tool in custom calls returns True."""
        mock_registry = Mock()
        # Use custom terminal tools since there are no default terminal tools
        executor = ToolExecutor(mock_registry, terminal_tools={"test_terminal_tool"})
        session = Mock()
        
        custom_calls = [{"name": "test_terminal_tool", "arguments": {"param": "value"}}]
        
        mock_registry.normalize_args.return_value = {"param": "value"}
        mock_registry.validate_args.return_value = (True, None)
        mock_registry.execute.return_value = "Executed"
        mock_describe.return_value = "Test terminal"
        mock_confirm.return_value = True
        
        result = executor.execute_custom_calls(custom_calls, session)
        
        # Should return True for terminal tool
        assert result is True
        
    @patch("ayder_cli.services.tools.executor.describe_tool_action")
    @patch("ayder_cli.services.tools.executor.confirm_with_diff")
    @patch("ayder_cli.services.tools.executor.prepare_new_content")
    @patch("ayder_cli.services.tools.executor.print_tool_result")
    def test_handle_custom_calls_write_file_with_diff(
        self, mock_print_result, mock_prepare, mock_confirm_diff, mock_describe
    ):
        """Test write_file in custom calls uses diff preview."""
        mock_registry = Mock()
        executor = ToolExecutor(mock_registry)
        session = Mock()

        custom_calls = [{"name": "write_file", "arguments": {"file_path": "test.txt", "content": "hello"}}]

        mock_registry.normalize_args.return_value = {"file_path": "test.txt", "content": "hello"}
        mock_registry.validate_args.return_value = (True, None)
        mock_registry.execute.return_value = "Successfully wrote to file"
        mock_describe.return_value = "Write file"
        mock_prepare.return_value = "hello"
        mock_confirm_diff.return_value = True

        result = executor.execute_custom_calls(custom_calls, session)

        # Verify confirm_with_diff was called for write_file
        mock_confirm_diff.assert_called_once_with("test.txt", "hello", "Write file")
        assert result is False  # Not a terminal tool


class TestExecuteSingleCall:
    """Tests for the unified _execute_single_call() method."""

    @patch("ayder_cli.services.tools.executor.confirm_tool_call")
    @patch("ayder_cli.services.tools.executor.describe_tool_action")
    @patch("ayder_cli.services.tools.executor.print_tool_result")
    def test_execute_single_call_success(self, mock_print_result, mock_describe, mock_confirm):
        """Normal tool execution returns ('success', result)."""
        mock_registry = Mock()
        executor = ToolExecutor(mock_registry)

        mock_registry.normalize_args.return_value = {"directory": "."}
        mock_registry.validate_args.return_value = (True, None)
        mock_registry.execute.return_value = "file1.txt\nfile2.txt"
        mock_describe.return_value = "List files in ."
        mock_confirm.return_value = True

        outcome, value = executor._execute_single_call(
            "list_files", {"directory": "."}, set(), verbose=False
        )

        assert outcome == "success"
        assert "file1.txt" in value
        mock_registry.execute.assert_called_once_with("list_files", {"directory": "."})
        mock_print_result.assert_called_once()

    def test_execute_single_call_normalize_error(self):
        """ValueError from normalize_args returns ('error', msg)."""
        mock_registry = Mock()
        executor = ToolExecutor(mock_registry)

        mock_registry.normalize_args.side_effect = ValueError("Path traversal blocked")

        outcome, value = executor._execute_single_call(
            "read_file", {"file_path": "../../etc/passwd"}, set(), verbose=False
        )

        assert outcome == "error"
        assert "Path traversal blocked" in value
        mock_registry.validate_args.assert_not_called()
        mock_registry.execute.assert_not_called()

    @patch("ayder_cli.services.tools.executor.describe_tool_action")
    def test_execute_single_call_validation_error(self, mock_describe):
        """Invalid args from validate_args returns ('error', msg)."""
        mock_registry = Mock()
        executor = ToolExecutor(mock_registry)

        mock_registry.normalize_args.return_value = {}
        mock_registry.validate_args.return_value = (False, "Missing required param")

        outcome, value = executor._execute_single_call(
            "read_file", {}, set(), verbose=False
        )

        assert outcome == "error"
        assert "Missing required param" in value
        mock_registry.execute.assert_not_called()

    @patch("ayder_cli.services.tools.executor.print_tool_skipped")
    @patch("ayder_cli.services.tools.executor.confirm_tool_call")
    @patch("ayder_cli.services.tools.executor.describe_tool_action")
    def test_execute_single_call_declined(self, mock_describe, mock_confirm, mock_skipped):
        """User declining confirmation returns ('declined', None)."""
        mock_registry = Mock()
        executor = ToolExecutor(mock_registry)

        mock_registry.normalize_args.return_value = {"directory": "."}
        mock_registry.validate_args.return_value = (True, None)
        mock_describe.return_value = "List files"
        mock_confirm.return_value = False

        outcome, value = executor._execute_single_call(
            "list_files", {"directory": "."}, set(), verbose=False
        )

        assert outcome == "declined"
        assert value is None
        mock_skipped.assert_called_once()
        mock_registry.execute.assert_not_called()

    @patch("ayder_cli.services.tools.executor.confirm_with_diff")
    @patch("ayder_cli.services.tools.executor.prepare_new_content")
    @patch("ayder_cli.services.tools.executor.describe_tool_action")
    @patch("ayder_cli.services.tools.executor.print_tool_result")
    def test_execute_single_call_write_file_diff(
        self, mock_print_result, mock_describe, mock_prepare, mock_confirm_diff
    ):
        """write_file uses confirm_with_diff and passes project_ctx."""
        mock_registry = Mock()
        mock_registry.project_ctx = Mock()
        executor = ToolExecutor(mock_registry)

        normalized = {"file_path": "test.txt", "content": "hello"}
        mock_registry.normalize_args.return_value = normalized
        mock_registry.validate_args.return_value = (True, None)
        mock_registry.execute.return_value = "Successfully wrote to file"
        mock_describe.return_value = "Write file"
        mock_prepare.return_value = "hello"
        mock_confirm_diff.return_value = True

        outcome, value = executor._execute_single_call(
            "write_file", {"file_path": "test.txt", "content": "hello"}, set(), verbose=False
        )

        assert outcome == "success"
        # Verify project_ctx is passed to prepare_new_content (bug fix)
        mock_prepare.assert_called_once_with("write_file", normalized, mock_registry.project_ctx)
        mock_confirm_diff.assert_called_once_with("test.txt", "hello", "Write file")

    @patch("ayder_cli.services.tools.executor.describe_tool_action")
    @patch("ayder_cli.services.tools.executor.print_tool_result")
    def test_execute_single_call_auto_approved(self, mock_print_result, mock_describe):
        """Permission flag skips confirmation entirely."""
        mock_registry = Mock()
        executor = ToolExecutor(mock_registry)

        mock_registry.normalize_args.return_value = {"directory": "."}
        mock_registry.validate_args.return_value = (True, None)
        mock_registry.execute.return_value = "file1.txt"
        mock_describe.return_value = "List files"

        # "r" permission matches the list_files tool permission
        outcome, value = executor._execute_single_call(
            "list_files", {"directory": "."}, {"r"}, verbose=False
        )

        assert outcome == "success"
        assert "file1.txt" in value
        # confirm_tool_call should NOT have been called (auto-approved)
        mock_registry.execute.assert_called_once()

    @patch("ayder_cli.services.tools.executor.print_file_content")
    @patch("ayder_cli.services.tools.executor.confirm_with_diff")
    @patch("ayder_cli.services.tools.executor.prepare_new_content")
    @patch("ayder_cli.services.tools.executor.describe_tool_action")
    @patch("ayder_cli.services.tools.executor.print_tool_result")
    def test_execute_single_call_verbose_write(
        self, mock_print_result, mock_describe, mock_prepare, mock_confirm_diff, mock_print_file
    ):
        """Verbose mode prints file content after successful write_file."""
        mock_registry = Mock()
        mock_registry.project_ctx = Mock()
        executor = ToolExecutor(mock_registry)

        normalized = {"file_path": "out.py", "content": "print('hi')"}
        mock_registry.normalize_args.return_value = normalized
        mock_registry.validate_args.return_value = (True, None)
        mock_registry.execute.return_value = ToolSuccess("Successfully wrote to file")
        mock_describe.return_value = "Write file"
        mock_prepare.return_value = "print('hi')"
        mock_confirm_diff.return_value = True

        outcome, value = executor._execute_single_call(
            "write_file", {"file_path": "out.py", "content": "print('hi')"}, set(), verbose=True
        )

        assert outcome == "success"
        mock_print_file.assert_called_once_with("out.py")
