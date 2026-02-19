"""Tests for ToolExecutor service."""

from unittest.mock import Mock, patch

from ayder_cli.services.tools.executor import ToolExecutor, TERMINAL_TOOLS
from ayder_cli.services.interactions import InteractionSink, ConfirmationPolicy


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

    def test_handle_tool_call(self):
        """Test handling a tool call with injected interfaces."""
        from ayder_cli.application.execution_policy import ExecutionResult

        mock_registry = Mock()
        sink = Mock(spec=InteractionSink)
        policy = Mock(spec=ConfirmationPolicy)
        policy.confirm_action.return_value = True
        executor = ToolExecutor(mock_registry, interaction_sink=sink, confirmation_policy=policy)

        mock_tool_call = Mock()
        mock_tool_call.id = "call_123"
        mock_tool_call.function.name = "list_files"
        mock_tool_call.function.arguments = '{"directory": "."}'

        mock_registry.normalize_args.return_value = {"directory": "."}
        fake_exec_result = ExecutionResult(success=True, result="file1.txt\nfile2.txt")

        with patch(
            "ayder_cli.application.execution_policy.ExecutionPolicy.execute_with_registry",
            return_value=fake_exec_result,
        ):
            result = executor._handle_tool_call(mock_tool_call, granted_permissions={"r"}, verbose=False)

        assert result is not None
        assert result["role"] == "tool"
        assert result["tool_call_id"] == "call_123"
        assert result["name"] == "list_files"
        assert "file1.txt" in result["content"]

    def test_handle_tool_call_declined(self):
        """Test handling a declined tool call."""
        mock_registry = Mock()
        sink = Mock(spec=InteractionSink)
        policy = Mock(spec=ConfirmationPolicy)
        policy.confirm_action.return_value = False
        executor = ToolExecutor(mock_registry, interaction_sink=sink, confirmation_policy=policy)

        mock_tool_call = Mock()
        mock_tool_call.id = "call_123"
        mock_tool_call.function.name = "list_files"
        mock_tool_call.function.arguments = '{"directory": "."}'

        mock_registry.normalize_args.return_value = {"directory": "."}
        mock_registry.validate_args.return_value = (True, None)

        result = executor._handle_tool_call(mock_tool_call, granted_permissions=set(), verbose=False)

        assert result is None
        sink.on_tool_skipped.assert_called_once()

    def test_execute_tool_calls_with_declined_tool(self):
        """Test that declined tool stops the loop."""
        mock_registry = Mock()
        executor = ToolExecutor(mock_registry)
        session = Mock()
        session.messages = []

        mock_tool_call = Mock()

        with patch.object(executor, "_handle_tool_call", return_value=None):
            result = executor.execute_tool_calls([mock_tool_call], session)

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

        assert result is False
        assert session.append_raw.call_count == 2
        session.append_raw.assert_any_call(result_msg1)
        session.append_raw.assert_any_call(result_msg2)

    def test_handle_custom_calls_validation_error(self):
        """Test validation error in custom calls stops execution."""
        mock_registry = Mock()
        executor = ToolExecutor(mock_registry)
        session = Mock()
        session.messages = []

        custom_calls = [{"name": "invalid_tool", "arguments": {}}]

        mock_registry.normalize_args.return_value = {}

        result = executor.execute_custom_calls(custom_calls, session)

        assert result is True
        # Error message should mention the tool name
        call_args = session.add_message.call_args
        assert call_args is not None
        assert "invalid_tool" in call_args[0][1]

    def test_handle_custom_calls_declined(self):
        """Test declined custom call stops execution."""
        mock_registry = Mock()
        sink = Mock(spec=InteractionSink)
        policy = Mock(spec=ConfirmationPolicy)
        policy.confirm_action.return_value = False
        executor = ToolExecutor(mock_registry, interaction_sink=sink, confirmation_policy=policy)
        session = Mock()

        custom_calls = [{"name": "list_files", "arguments": {"directory": "."}}]

        mock_registry.normalize_args.return_value = {"directory": "."}
        mock_registry.validate_args.return_value = (True, None)

        result = executor.execute_custom_calls(custom_calls, session)

        assert result is True
        sink.on_tool_skipped.assert_called_once()

    def test_handle_custom_calls_with_terminal_tool(self):
        """Test terminal tool in custom calls returns True."""
        mock_registry = Mock()
        sink = Mock(spec=InteractionSink)
        policy = Mock(spec=ConfirmationPolicy)
        policy.confirm_action.return_value = True
        executor = ToolExecutor(
            mock_registry,
            terminal_tools={"test_terminal_tool"},
            interaction_sink=sink,
            confirmation_policy=policy,
        )
        session = Mock()

        custom_calls = [{"name": "test_terminal_tool", "arguments": {"param": "value"}}]

        mock_registry.normalize_args.return_value = {"param": "value"}
        mock_registry.validate_args.return_value = (True, None)
        mock_registry.execute.return_value = "Executed"

        result = executor.execute_custom_calls(custom_calls, session)

        assert result is True

    def test_handle_custom_calls_write_file_with_diff(self):
        """Test write_file in custom calls uses diff preview when permission not pre-granted."""
        from ayder_cli.application.execution_policy import ExecutionResult

        mock_registry = Mock()
        mock_registry.project_ctx = Mock()
        sink = Mock(spec=InteractionSink)
        policy = Mock(spec=ConfirmationPolicy)
        policy.confirm_action.return_value = True
        policy.confirm_file_diff.return_value = True
        executor = ToolExecutor(
            mock_registry,
            interaction_sink=sink,
            confirmation_policy=policy,
        )
        session = Mock()

        custom_calls = [{"name": "write_file", "arguments": {"file_path": "test.txt", "content": "hello"}}]

        mock_registry.normalize_args.return_value = {"file_path": "test.txt", "content": "hello"}
        fake_result = ExecutionResult(success=True, result="Successfully wrote to file")

        # granted_permissions=set() means write_file is NOT auto-approved → triggers diff dialog
        with patch("ayder_cli.services.tools.executor.prepare_new_content", return_value="hello"):
            with patch(
                "ayder_cli.application.execution_policy.ExecutionPolicy.execute_with_registry",
                return_value=fake_result,
            ):
                result = executor.execute_custom_calls(custom_calls, session, granted_permissions=set())

        policy.confirm_file_diff.assert_called_once()
        assert result is False


class TestExecuteSingleCall:
    """Tests for the unified _execute_single_call() method."""

    def test_execute_single_call_success(self):
        """Normal tool execution returns ('success', result)."""
        from ayder_cli.application.execution_policy import ExecutionResult

        mock_registry = Mock()
        sink = Mock(spec=InteractionSink)
        policy = Mock(spec=ConfirmationPolicy)
        policy.confirm_action.return_value = True
        executor = ToolExecutor(mock_registry, interaction_sink=sink, confirmation_policy=policy)

        mock_registry.normalize_args.return_value = {"directory": "."}
        fake_result = ExecutionResult(success=True, result="file1.txt\nfile2.txt")

        with patch(
            "ayder_cli.application.execution_policy.ExecutionPolicy.execute_with_registry",
            return_value=fake_result,
        ):
            outcome, value = executor._execute_single_call(
                "list_files", {"directory": "."}, {"r"}, verbose=False
            )

        assert outcome == "success"
        assert "file1.txt" in value
        sink.on_tool_result.assert_called_once()

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

    def test_execute_single_call_validation_error(self):
        """ValidationAuthority rejects unknown/invalid tool returns ('error', msg)."""
        mock_registry = Mock()
        executor = ToolExecutor(mock_registry)

        # "read_file" requires "file_path" — passing empty args triggers validation error
        mock_registry.normalize_args.return_value = {}

        outcome, value = executor._execute_single_call(
            "read_file", {}, {"r"}, verbose=False
        )

        assert outcome == "error"
        # ValidationAuthority reports missing required arg
        assert value is not None

    def test_execute_single_call_declined(self):
        """User declining confirmation returns ('declined', None)."""
        mock_registry = Mock()
        sink = Mock(spec=InteractionSink)
        policy = Mock(spec=ConfirmationPolicy)
        policy.confirm_action.return_value = False
        executor = ToolExecutor(mock_registry, interaction_sink=sink, confirmation_policy=policy)

        mock_registry.normalize_args.return_value = {"directory": "."}

        outcome, value = executor._execute_single_call(
            "list_files", {"directory": "."}, set(), verbose=False
        )

        assert outcome == "declined"
        assert value is None
        sink.on_tool_skipped.assert_called_once()

    def test_execute_single_call_write_file_diff(self):
        """write_file uses confirm_file_diff."""
        from ayder_cli.application.execution_policy import ExecutionResult

        mock_registry = Mock()
        mock_registry.project_ctx = Mock()
        sink = Mock(spec=InteractionSink)
        policy = Mock(spec=ConfirmationPolicy)
        policy.confirm_action.return_value = True
        policy.confirm_file_diff.return_value = True
        executor = ToolExecutor(mock_registry, interaction_sink=sink, confirmation_policy=policy)

        normalized = {"file_path": "test.txt", "content": "hello"}
        mock_registry.normalize_args.return_value = normalized
        fake_result = ExecutionResult(success=True, result="Successfully wrote to file")

        # Use empty permissions so write_file requires confirmation → triggers diff dialog
        with patch("ayder_cli.services.tools.executor.prepare_new_content", return_value="hello") as mock_prepare:
            with patch(
                "ayder_cli.application.execution_policy.ExecutionPolicy.execute_with_registry",
                return_value=fake_result,
            ):
                outcome, value = executor._execute_single_call(
                    "write_file", {"file_path": "test.txt", "content": "hello"}, set(), verbose=False
                )

        assert outcome == "success"
        mock_prepare.assert_called_once_with("write_file", normalized, mock_registry.project_ctx)
        policy.confirm_file_diff.assert_called_once()

    def test_execute_single_call_auto_approved(self):
        """Permission flag skips confirmation entirely."""
        from ayder_cli.application.execution_policy import ExecutionResult

        mock_registry = Mock()
        sink = Mock(spec=InteractionSink)
        policy = Mock(spec=ConfirmationPolicy)
        executor = ToolExecutor(mock_registry, interaction_sink=sink, confirmation_policy=policy)

        mock_registry.normalize_args.return_value = {"directory": "."}
        fake_result = ExecutionResult(success=True, result="file1.txt")

        with patch(
            "ayder_cli.application.execution_policy.ExecutionPolicy.execute_with_registry",
            return_value=fake_result,
        ):
            outcome, value = executor._execute_single_call(
                "list_files", {"directory": "."}, {"r"}, verbose=False
            )

        assert outcome == "success"
        assert "file1.txt" in value
        policy.confirm_action.assert_not_called()

    def test_execute_single_call_verbose_write(self):
        """Verbose mode calls sink.on_file_preview after successful write_file."""
        from ayder_cli.application.execution_policy import ExecutionResult

        mock_registry = Mock()
        mock_registry.project_ctx = Mock()
        sink = Mock(spec=InteractionSink)
        policy = Mock(spec=ConfirmationPolicy)
        policy.confirm_action.return_value = True
        policy.confirm_file_diff.return_value = True
        executor = ToolExecutor(mock_registry, interaction_sink=sink, confirmation_policy=policy)

        normalized = {"file_path": "out.py", "content": "print('hi')"}
        mock_registry.normalize_args.return_value = normalized
        fake_result = ExecutionResult(success=True, result="Successfully wrote to file")

        with patch("ayder_cli.services.tools.executor.prepare_new_content", return_value="print('hi')"):
            with patch(
                "ayder_cli.application.execution_policy.ExecutionPolicy.execute_with_registry",
                return_value=fake_result,
            ):
                outcome, value = executor._execute_single_call(
                    "write_file", {"file_path": "out.py", "content": "print('hi')"}, {"w"}, verbose=True
                )

        assert outcome == "success"
        sink.on_file_preview.assert_called_once_with("out.py")
