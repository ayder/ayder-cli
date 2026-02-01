"""Tests for client.py module."""

import pytest
from unittest.mock import Mock, patch, MagicMock, call
import json

from ayder_cli import client


class TestRunChatExitHandling:
    """Test exit command handling in run_chat()."""

    @patch("ayder_cli.client.load_config")
    @patch("ayder_cli.client.OpenAI")
    @patch("ayder_cli.client.PromptSession")
    @patch("ayder_cli.client.print_welcome_banner")
    @patch("builtins.print")
    def test_exit_command_quits(self, mock_print, mock_banner, mock_session, mock_openai, mock_config):
        """Test that 'exit' command quits the chat loop."""
        mock_config.return_value = {
            "base_url": "http://test.com",
            "api_key": "test-key",
            "model": "test-model",
            "num_ctx": 4096,
            "verbose": False
        }
        mock_instance = Mock()
        mock_instance.prompt.side_effect = ["exit"]
        mock_session.return_value = mock_instance

        client.run_chat()

        # Verify goodbye message was printed
        mock_print.assert_any_call("\n\033[33mGoodbye!\033[0m\n")

    @patch("ayder_cli.client.load_config")
    @patch("ayder_cli.client.OpenAI")
    @patch("ayder_cli.client.PromptSession")
    @patch("ayder_cli.client.print_welcome_banner")
    @patch("builtins.print")
    def test_quit_command_quits(self, mock_print, mock_banner, mock_session, mock_openai, mock_config):
        """Test that 'quit' command quits the chat loop."""
        mock_config.return_value = {
            "base_url": "http://test.com",
            "api_key": "test-key",
            "model": "test-model",
            "num_ctx": 4096,
            "verbose": False
        }
        mock_instance = Mock()
        mock_instance.prompt.side_effect = ["quit"]
        mock_session.return_value = mock_instance

        client.run_chat()

        # Verify goodbye message was printed
        mock_print.assert_any_call("\n\033[33mGoodbye!\033[0m\n")

    @patch("ayder_cli.client.load_config")
    @patch("ayder_cli.client.OpenAI")
    @patch("ayder_cli.client.PromptSession")
    @patch("ayder_cli.client.print_welcome_banner")
    @patch("builtins.print")
    def test_exit_case_insensitive(self, mock_print, mock_banner, mock_session, mock_openai, mock_config):
        """Test that 'EXIT' and 'Exit' also quit."""
        mock_config.return_value = {
            "base_url": "http://test.com",
            "api_key": "test-key",
            "model": "test-model",
            "num_ctx": 4096,
            "verbose": False
        }
        mock_instance = Mock()
        mock_instance.prompt.side_effect = ["EXIT"]
        mock_session.return_value = mock_instance

        client.run_chat()

        mock_print.assert_any_call("\n\033[33mGoodbye!\033[0m\n")

    @patch("ayder_cli.client.load_config")
    @patch("ayder_cli.client.OpenAI")
    @patch("ayder_cli.client.PromptSession")
    @patch("ayder_cli.client.print_welcome_banner")
    def test_empty_input_continues(self, mock_banner, mock_session, mock_openai, mock_config):
        """Test that empty input continues to next iteration."""
        mock_config.return_value = {
            "base_url": "http://test.com",
            "api_key": "test-key",
            "model": "test-model",
            "num_ctx": 4096,
            "verbose": False
        }
        mock_instance = Mock()
        mock_instance.prompt.side_effect = ["", "", "exit"]
        mock_session.return_value = mock_instance

        client.run_chat()

        # Should have prompted 3 times (2 empty, 1 exit)
        assert mock_instance.prompt.call_count == 3


class TestRunChatExceptionHandling:
    """Test exception handling in run_chat()."""

    @patch("ayder_cli.client.load_config")
    @patch("ayder_cli.client.OpenAI")
    @patch("ayder_cli.client.PromptSession")
    @patch("ayder_cli.client.print_welcome_banner")
    @patch("ayder_cli.client.draw_box")
    @patch("builtins.print")
    def test_keyboard_interrupt(self, mock_print, mock_draw_box, mock_banner, mock_session, mock_openai, mock_config):
        """Test KeyboardInterrupt handling shows message and continues."""
        mock_config.return_value = {
            "base_url": "http://test.com",
            "api_key": "test-key",
            "model": "test-model",
            "num_ctx": 4096,
            "verbose": False
        }
        mock_instance = Mock()
        mock_instance.prompt.side_effect = [KeyboardInterrupt(), "exit"]
        mock_session.return_value = mock_instance

        client.run_chat()

        # Verify the KeyboardInterrupt message
        mock_print.assert_any_call("\n\033[33m\nUse 'exit' or Ctrl+D to quit.\033[0m")

    @patch("ayder_cli.client.load_config")
    @patch("ayder_cli.client.OpenAI")
    @patch("ayder_cli.client.PromptSession")
    @patch("ayder_cli.client.print_welcome_banner")
    @patch("ayder_cli.client.draw_box")
    @patch("builtins.print")
    def test_eof_error(self, mock_print, mock_draw_box, mock_banner, mock_session, mock_openai, mock_config):
        """Test EOFError handling (Ctrl+D) quits gracefully."""
        mock_config.return_value = {
            "base_url": "http://test.com",
            "api_key": "test-key",
            "model": "test-model",
            "num_ctx": 4096,
            "verbose": False
        }
        mock_instance = Mock()
        mock_instance.prompt.side_effect = [EOFError()]
        mock_session.return_value = mock_instance

        client.run_chat()

        mock_print.assert_any_call("\n\033[33mGoodbye!\033[0m\n")

    @patch("ayder_cli.client.load_config")
    @patch("ayder_cli.client.OpenAI")
    @patch("ayder_cli.client.PromptSession")
    @patch("ayder_cli.client.print_welcome_banner")
    @patch("ayder_cli.client.draw_box")
    @patch("builtins.print")
    def test_general_exception(self, mock_print, mock_draw_box, mock_banner, mock_session, mock_openai, mock_config):
        """Test general exception handling shows error box."""
        mock_config.return_value = {
            "base_url": "http://test.com",
            "api_key": "test-key",
            "model": "test-model",
            "num_ctx": 4096,
            "verbose": False
        }
        mock_instance = Mock()
        mock_instance.prompt.side_effect = [Exception("Test error"), "exit"]
        mock_session.return_value = mock_instance

        client.run_chat()

        # Verify draw_box was called with error message
        mock_draw_box.assert_called_once()
        call_args = mock_draw_box.call_args
        assert "Test error" in call_args[0][0]
        assert call_args[1]["title"] == "Error"


class TestRunChatSlashCommands:
    """Test slash command handling in run_chat()."""

    @patch("ayder_cli.client.load_config")
    @patch("ayder_cli.client.OpenAI")
    @patch("ayder_cli.client.PromptSession")
    @patch("ayder_cli.client.print_welcome_banner")
    @patch("ayder_cli.client.handle_command")
    def test_slash_command_handled(self, mock_handle, mock_banner, mock_session, mock_openai, mock_config):
        """Test that slash commands call handle_command."""
        mock_config.return_value = {
            "base_url": "http://test.com",
            "api_key": "test-key",
            "model": "test-model",
            "num_ctx": 4096,
            "verbose": False
        }
        mock_instance = Mock()
        mock_instance.prompt.side_effect = ["/help", "exit"]
        mock_session.return_value = mock_instance
        mock_handle.return_value = True

        client.run_chat()

        # Verify handle_command was called
        mock_handle.assert_called_once()
        call_args = mock_handle.call_args
        assert call_args[0][0] == "/help"


class TestRunChatToolExecution:
    """Test tool execution flow in run_chat()."""

    @patch("ayder_cli.client.load_config")
    @patch("ayder_cli.client.OpenAI")
    @patch("ayder_cli.client.PromptSession")
    @patch("ayder_cli.client.print_welcome_banner")
    @patch("ayder_cli.client.print_running")
    @patch("ayder_cli.client.print_assistant_message")
    @patch("ayder_cli.client.describe_tool_action")
    @patch("ayder_cli.client.preview_file_modification")
    @patch("ayder_cli.client.confirm_tool_call")
    @patch("ayder_cli.client.fs_tools.execute_tool_call")
    @patch("ayder_cli.client.print_tool_result")
    def test_standard_tool_call_flow(self, mock_print_result, mock_execute, mock_confirm,
                                      mock_preview, mock_describe, mock_print_msg, mock_running,
                                      mock_banner, mock_session, mock_openai, mock_config):
        """Test standard tool call flow with user confirmation."""
        mock_config.return_value = {
            "base_url": "http://test.com",
            "api_key": "test-key",
            "model": "test-model",
            "num_ctx": 4096,
            "verbose": False
        }

        # Mock the session
        mock_instance = Mock()
        mock_instance.prompt.side_effect = ["test input", "exit"]
        mock_session.return_value = mock_instance

        # Mock OpenAI client
        mock_client = Mock()
        mock_openai.return_value = mock_client

        # Create mock tool call for first response
        mock_tool_call = Mock()
        mock_tool_call.id = "call_123"
        mock_tool_call.function.name = "read_file"
        mock_tool_call.function.arguments = '{"file_path": "/test/file.txt"}'

        mock_msg_with_tool = Mock()
        mock_msg_with_tool.content = None
        mock_msg_with_tool.tool_calls = [mock_tool_call]

        mock_response_with_tool = Mock()
        mock_response_with_tool.choices = [Mock()]
        mock_response_with_tool.choices[0].message = mock_msg_with_tool

        # Create mock response without tools (to end the loop)
        mock_msg_no_tool = Mock()
        mock_msg_no_tool.content = "Done reading"
        mock_msg_no_tool.tool_calls = None

        mock_response_no_tool = Mock()
        mock_response_no_tool.choices = [Mock()]
        mock_response_no_tool.choices[0].message = mock_msg_no_tool

        # First call returns tool, subsequent calls return no tool
        mock_client.chat.completions.create.side_effect = [
            mock_response_with_tool,
            mock_response_no_tool
        ]

        # Mock confirmations and execution
        mock_describe.return_value = "Read file /test/file.txt"
        mock_preview.return_value = False  # Not a file modification tool
        mock_confirm.return_value = True
        mock_execute.return_value = "File content here"

        client.run_chat()

        # Verify preview was called
        mock_preview.assert_called_once_with("read_file", '{"file_path": "/test/file.txt"}')
        # Verify tool was executed once
        mock_execute.assert_called_once_with("read_file", '{"file_path": "/test/file.txt"}')
        mock_print_result.assert_called_once_with("File content here")

    @patch("ayder_cli.client.load_config")
    @patch("ayder_cli.client.OpenAI")
    @patch("ayder_cli.client.PromptSession")
    @patch("ayder_cli.client.print_welcome_banner")
    @patch("ayder_cli.client.print_running")
    @patch("ayder_cli.client.describe_tool_action")
    @patch("ayder_cli.client.preview_file_modification")
    @patch("ayder_cli.client.confirm_tool_call")
    @patch("ayder_cli.client.fs_tools.execute_tool_call")
    @patch("ayder_cli.client.print_tool_result")
    @patch("ayder_cli.client.draw_box")
    def test_declined_tool_call(self, mock_draw_box, mock_print_result, mock_execute,
                                 mock_confirm, mock_preview, mock_describe, mock_running,
                                 mock_banner, mock_session, mock_openai, mock_config):
        """Test that declined standard tool calls show skipped message and send decline feedback."""
        mock_config.return_value = {
            "base_url": "http://test.com",
            "api_key": "test-key",
            "model": "test-model",
            "num_ctx": 4096,
            "verbose": False
        }

        mock_instance = Mock()
        mock_instance.prompt.side_effect = ["test", "exit"]
        mock_session.return_value = mock_instance

        mock_client = Mock()
        mock_openai.return_value = mock_client

        mock_tool_call = Mock()
        mock_tool_call.id = "call_123"
        mock_tool_call.function.name = "write_file"
        mock_tool_call.function.arguments = '{"file_path": "/test.txt", "content": "hi"}'

        mock_msg = Mock()
        mock_msg.content = None
        mock_msg.tool_calls = [mock_tool_call]

        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message = mock_msg

        mock_client.chat.completions.create.return_value = mock_response

        mock_describe.return_value = "Write to /test.txt"
        mock_preview.return_value = True  # Is a file modification tool
        mock_confirm.return_value = False  # User declines

        client.run_chat()

        # Verify preview was called
        mock_preview.assert_called_once_with("write_file", '{"file_path": "/test.txt", "content": "hi"}')
        # Verify skipped message was shown
        mock_draw_box.assert_called_with("Tool call skipped by user.", title="Skipped", width=80, color_code="33")
        # Tool should not be executed
        mock_execute.assert_not_called()

        # Verify that run_chat was called (it went through the flow)
        # We can't easily inspect the messages list, but we verified the decline flow worked

    @patch("ayder_cli.client.load_config")
    @patch("ayder_cli.client.OpenAI")
    @patch("ayder_cli.client.PromptSession")
    @patch("ayder_cli.client.print_welcome_banner")
    @patch("ayder_cli.client.print_running")
    @patch("ayder_cli.client.describe_tool_action")
    @patch("ayder_cli.client.preview_file_modification")
    @patch("ayder_cli.client.confirm_tool_call")
    @patch("ayder_cli.client.fs_tools.execute_tool_call")
    @patch("ayder_cli.client.print_tool_result")
    @patch("ayder_cli.client.draw_box")
    def test_declined_standard_tool_call_sends_feedback(self, mock_draw_box, mock_print_result, mock_execute,
                                                         mock_confirm, mock_preview, mock_describe, mock_running,
                                                         mock_banner, mock_session, mock_openai, mock_config):
        """Test that declined standard tool calls append decline message to messages list."""
        mock_config.return_value = {
            "base_url": "http://test.com",
            "api_key": "test-key",
            "model": "test-model",
            "num_ctx": 4096,
            "verbose": False
        }

        mock_instance = Mock()
        mock_instance.prompt.side_effect = ["test", "exit"]
        mock_session.return_value = mock_instance

        mock_client = Mock()
        mock_openai.return_value = mock_client

        mock_tool_call = Mock()
        mock_tool_call.id = "call_123"
        mock_tool_call.function.name = "read_file"
        mock_tool_call.function.arguments = '{"file_path": "/test.txt"}'

        mock_msg_with_tool = Mock()
        mock_msg_with_tool.content = None
        mock_msg_with_tool.tool_calls = [mock_tool_call]

        mock_response_with_tool = Mock()
        mock_response_with_tool.choices = [Mock()]
        mock_response_with_tool.choices[0].message = mock_msg_with_tool

        # Only one API call (tool declined, loop ends)
        mock_client.chat.completions.create.return_value = mock_response_with_tool

        mock_describe.return_value = "Read file /test.txt"
        mock_preview.return_value = False  # Not a file modification tool
        mock_confirm.return_value = False  # User declines

        # We need to capture the messages list to verify the decline message was added
        messages_captured = []

        def capture_messages(*args, **kwargs):
            messages_captured.append(kwargs.get('messages', []))
            return mock_response_with_tool

        mock_client.chat.completions.create.side_effect = capture_messages

        client.run_chat()

        # Verify tool was not executed
        mock_execute.assert_not_called()

        # Verify API was called once
        assert mock_client.chat.completions.create.call_count == 1

        # Verify the decline message was appended to the messages list
        assert len(messages_captured) > 0
        messages = messages_captured[0]

        # Check for decline message with correct structure
        decline_msg = None
        for msg in messages:
            if isinstance(msg, dict) and msg.get('role') == 'tool' and msg.get('tool_call_id') == 'call_123':
                decline_msg = msg
                break

        assert decline_msg is not None, "Decline message not found in messages list"
        assert decline_msg['name'] == 'read_file'
        assert 'declined by user' in decline_msg['content']

    @patch("ayder_cli.client.load_config")
    @patch("ayder_cli.client.OpenAI")
    @patch("ayder_cli.client.PromptSession")
    @patch("ayder_cli.client.print_welcome_banner")
    @patch("ayder_cli.client.print_running")
    @patch("ayder_cli.client.describe_tool_action")
    @patch("ayder_cli.client.preview_file_modification")
    @patch("ayder_cli.client.confirm_tool_call")
    @patch("ayder_cli.client.fs_tools.execute_tool_call")
    @patch("ayder_cli.client.print_tool_result")
    def test_terminal_tool_stops_loop(self, mock_print_result, mock_execute, mock_confirm,
                                       mock_preview, mock_describe, mock_running, mock_banner,
                                       mock_session, mock_openai, mock_config):
        """Test that terminal tools stop the tool execution loop."""
        mock_config.return_value = {
            "base_url": "http://test.com",
            "api_key": "test-key",
            "model": "test-model",
            "num_ctx": 4096,
            "verbose": False
        }

        mock_instance = Mock()
        mock_instance.prompt.side_effect = ["create a task", "exit"]
        mock_session.return_value = mock_instance

        mock_client = Mock()
        mock_openai.return_value = mock_client

        mock_tool_call = Mock()
        mock_tool_call.id = "call_123"
        mock_tool_call.function.name = "create_task"
        mock_tool_call.function.arguments = '{"title": "Test", "description": "Test task"}'

        mock_msg = Mock()
        mock_msg.content = None
        mock_msg.tool_calls = [mock_tool_call]

        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message = mock_msg

        mock_client.chat.completions.create.return_value = mock_response

        mock_describe.return_value = "Create task"
        mock_preview.return_value = False  # Not a file modification tool
        mock_confirm.return_value = True
        mock_execute.return_value = "Task created"

        client.run_chat()

        # Verify the tool was executed
        mock_execute.assert_called_once()
        # Only one completion call should be made (terminal tool stops loop)
        assert mock_client.chat.completions.create.call_count == 1

    @patch("ayder_cli.client.load_config")
    @patch("ayder_cli.client.OpenAI")
    @patch("ayder_cli.client.PromptSession")
    @patch("ayder_cli.client.print_welcome_banner")
    @patch("ayder_cli.client.print_running")
    @patch("ayder_cli.client.print_assistant_message")
    def test_conversation_no_tools(self, mock_print_msg, mock_running, mock_banner,
                                    mock_session, mock_openai, mock_config):
        """Test simple conversation without tools."""
        mock_config.return_value = {
            "base_url": "http://test.com",
            "api_key": "test-key",
            "model": "test-model",
            "num_ctx": 4096,
            "verbose": False
        }
        
        mock_instance = Mock()
        mock_instance.prompt.side_effect = ["hello", "exit"]
        mock_session.return_value = mock_instance

        mock_client = Mock()
        mock_openai.return_value = mock_client
        
        mock_msg = Mock()
        mock_msg.content = "Hello there!"
        mock_msg.tool_calls = None
        
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message = mock_msg
        
        mock_client.chat.completions.create.return_value = mock_response

        client.run_chat()

        # Verify assistant message was printed
        mock_print_msg.assert_called_once_with("Hello there!")


class TestRunChatVerboseMode:
    """Test verbose mode functionality in run_chat()."""

    @patch("ayder_cli.client.load_config")
    @patch("ayder_cli.client.OpenAI")
    @patch("ayder_cli.client.PromptSession")
    @patch("ayder_cli.client.print_welcome_banner")
    @patch("ayder_cli.client.print_running")
    @patch("ayder_cli.client.describe_tool_action")
    @patch("ayder_cli.client.preview_file_modification")
    @patch("ayder_cli.client.confirm_tool_call")
    @patch("ayder_cli.client.fs_tools.execute_tool_call")
    @patch("ayder_cli.client.print_tool_result")
    @patch("ayder_cli.client.print_file_content")
    def test_verbose_write_file_shows_content(self, mock_print_content, mock_print_result,
                                               mock_execute, mock_confirm, mock_preview,
                                               mock_describe, mock_running, mock_banner,
                                               mock_session, mock_openai, mock_config):
        """Test that verbose mode shows file content after write_file."""
        mock_config.return_value = {
            "base_url": "http://test.com",
            "api_key": "test-key",
            "model": "test-model",
            "num_ctx": 4096,
            "verbose": True  # Verbose mode enabled
        }

        mock_instance = Mock()
        mock_instance.prompt.side_effect = ["write something", "exit"]
        mock_session.return_value = mock_instance

        mock_client = Mock()
        mock_openai.return_value = mock_client

        mock_tool_call = Mock()
        mock_tool_call.id = "call_123"
        mock_tool_call.function.name = "write_file"
        mock_tool_call.function.arguments = '{"file_path": "/test/output.txt", "content": "test data"}'

        mock_msg_with_tool = Mock()
        mock_msg_with_tool.content = None
        mock_msg_with_tool.tool_calls = [mock_tool_call]

        mock_response_with_tool = Mock()
        mock_response_with_tool.choices = [Mock()]
        mock_response_with_tool.choices[0].message = mock_msg_with_tool

        # Create mock response without tools (to end the loop)
        mock_msg_no_tool = Mock()
        mock_msg_no_tool.content = "Done writing"
        mock_msg_no_tool.tool_calls = None

        mock_response_no_tool = Mock()
        mock_response_no_tool.choices = [Mock()]
        mock_response_no_tool.choices[0].message = mock_msg_no_tool

        # First call returns tool, second returns no tool
        mock_client.chat.completions.create.side_effect = [
            mock_response_with_tool,
            mock_response_no_tool
        ]

        mock_describe.return_value = "Write to /test/output.txt"
        mock_preview.return_value = True  # Is a file modification tool
        mock_confirm.return_value = True
        mock_execute.return_value = "Successfully wrote to /test/output.txt"

        client.run_chat()

        # Verify preview was called
        mock_preview.assert_called_once()
        # Verify file content was printed once
        mock_print_content.assert_called_once_with("/test/output.txt")

    @patch("ayder_cli.client.load_config")
    @patch("ayder_cli.client.OpenAI")
    @patch("ayder_cli.client.PromptSession")
    @patch("ayder_cli.client.print_welcome_banner")
    @patch("ayder_cli.client.print_running")
    @patch("ayder_cli.client.describe_tool_action")
    @patch("ayder_cli.client.preview_file_modification")
    @patch("ayder_cli.client.confirm_tool_call")
    @patch("ayder_cli.client.fs_tools.execute_tool_call")
    @patch("ayder_cli.client.print_tool_result")
    @patch("ayder_cli.client.print_file_content")
    def test_verbose_non_success_write(self, mock_print_content, mock_print_result,
                                        mock_execute, mock_confirm, mock_preview,
                                        mock_describe, mock_running, mock_banner,
                                        mock_session, mock_openai, mock_config):
        """Test verbose mode doesn't show content on failed write."""
        mock_config.return_value = {
            "base_url": "http://test.com",
            "api_key": "test-key",
            "model": "test-model",
            "num_ctx": 4096,
            "verbose": True
        }

        mock_instance = Mock()
        mock_instance.prompt.side_effect = ["write something", "exit"]
        mock_session.return_value = mock_instance

        mock_client = Mock()
        mock_openai.return_value = mock_client

        mock_tool_call = Mock()
        mock_tool_call.id = "call_123"
        mock_tool_call.function.name = "write_file"
        mock_tool_call.function.arguments = '{"file_path": "/test/output.txt", "content": "test"}'

        mock_msg = Mock()
        mock_msg.content = None
        mock_msg.tool_calls = [mock_tool_call]

        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message = mock_msg

        mock_client.chat.completions.create.return_value = mock_response

        mock_describe.return_value = "Write to /test/output.txt"
        mock_preview.return_value = True  # Is a file modification tool
        mock_confirm.return_value = True
        mock_execute.return_value = "Error: Permission denied"  # Not starting with "Successfully"

        client.run_chat()

        # File content should NOT be printed on error
        mock_print_content.assert_not_called()


    @patch("ayder_cli.client.load_config")
    @patch("ayder_cli.client.OpenAI")
    @patch("ayder_cli.client.PromptSession")
    @patch("ayder_cli.client.print_welcome_banner")
    @patch("ayder_cli.client.print_running")
    @patch("ayder_cli.client.parse_custom_tool_calls")
    @patch("ayder_cli.client.describe_tool_action")
    @patch("ayder_cli.client.preview_file_modification")
    @patch("ayder_cli.client.confirm_tool_call")
    @patch("ayder_cli.client.fs_tools.execute_tool_call")
    @patch("ayder_cli.client.print_tool_result")
    @patch("ayder_cli.client.draw_box")
    def test_declined_custom_tool_call_sends_feedback(self, mock_draw_box, mock_print_result, mock_execute,
                                                       mock_confirm, mock_preview, mock_describe, mock_parse,
                                                       mock_running, mock_banner, mock_session, mock_openai, mock_config):
        """Test that declined custom tool calls append decline feedback message."""
        mock_config.return_value = {
            "base_url": "http://test.com",
            "api_key": "test-key",
            "model": "test-model",
            "num_ctx": 4096,
            "verbose": False
        }

        mock_instance = Mock()
        mock_instance.prompt.side_effect = ["custom tool test", "exit"]
        mock_session.return_value = mock_instance

        mock_client = Mock()
        mock_openai.return_value = mock_client

        # Response with custom tool calls parsed from content
        mock_msg = Mock()
        mock_msg.content = "Let me help you with <function=read_file><parameter=file_path>/test.txt</parameter></function>"
        mock_msg.tool_calls = None  # No standard tool calls

        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message = mock_msg

        mock_client.chat.completions.create.return_value = mock_response

        # Return custom tool calls on first call, empty on second
        mock_parse.side_effect = [
            [{"name": "read_file", "arguments": {"file_path": "/test.txt"}}],
            []  # Empty on second iteration
        ]

        mock_describe.return_value = "Read file /test.txt"
        mock_preview.return_value = False  # Not a file modification tool
        mock_confirm.return_value = False  # User declines

        # Capture messages to verify decline message was added
        messages_captured = []

        def capture_messages(*args, **kwargs):
            messages_captured.append(kwargs.get('messages', []))
            return mock_response

        mock_client.chat.completions.create.side_effect = capture_messages

        client.run_chat()

        # Verify tool was not executed
        mock_execute.assert_not_called()

        # Verify API was called once
        assert mock_client.chat.completions.create.call_count == 1

        # Verify the decline message was appended
        assert len(messages_captured) > 0
        messages = messages_captured[0]

        # Check for decline message (user role for custom parsing)
        decline_msg = None
        for msg in messages:
            if isinstance(msg, dict) and msg.get('role') == 'user' and 'read_file' in msg.get('content', ''):
                if 'declined' in msg.get('content', '').lower():
                    decline_msg = msg
                    break

        assert decline_msg is not None, "Decline message not found in messages"
        assert 'declined' in decline_msg['content'].lower()


class TestRunChatCustomToolCalls:
    """Test custom tool call parsing in run_chat()."""

    @patch("ayder_cli.client.load_config")
    @patch("ayder_cli.client.OpenAI")
    @patch("ayder_cli.client.PromptSession")
    @patch("ayder_cli.client.print_welcome_banner")
    @patch("ayder_cli.client.print_running")
    @patch("ayder_cli.client.parse_custom_tool_calls")
    @patch("ayder_cli.client.describe_tool_action")
    @patch("ayder_cli.client.preview_file_modification")
    @patch("ayder_cli.client.confirm_tool_call")
    @patch("ayder_cli.client.fs_tools.execute_tool_call")
    @patch("ayder_cli.client.print_tool_result")
    def test_custom_tool_call_execution(self, mock_print_result, mock_execute, mock_confirm,
                                         mock_preview, mock_describe, mock_parse, mock_running,
                                         mock_banner, mock_session, mock_openai, mock_config):
        """Test execution of custom parsed tool calls."""
        mock_config.return_value = {
            "base_url": "http://test.com",
            "api_key": "test-key",
            "model": "test-model",
            "num_ctx": 4096,
            "verbose": False
        }

        mock_instance = Mock()
        mock_instance.prompt.side_effect = ["custom command", "exit"]
        mock_session.return_value = mock_instance

        mock_client = Mock()
        mock_openai.return_value = mock_client

        # First response has custom tool calls
        mock_msg_with_custom = Mock()
        mock_msg_with_custom.content = "Let me help you with that"
        mock_msg_with_custom.tool_calls = None  # No standard tool calls

        mock_response_with_custom = Mock()
        mock_response_with_custom.choices = [Mock()]
        mock_response_with_custom.choices[0].message = mock_msg_with_custom

        # Second response ends the loop
        mock_msg_no_tool = Mock()
        mock_msg_no_tool.content = "Done"
        mock_msg_no_tool.tool_calls = None

        mock_response_no_tool = Mock()
        mock_response_no_tool.choices = [Mock()]
        mock_response_no_tool.choices[0].message = mock_msg_no_tool

        mock_client.chat.completions.create.side_effect = [
            mock_response_with_custom,
            mock_response_no_tool
        ]

        # Return custom tool calls on first call, empty on second
        mock_parse.side_effect = [
            [{"name": "read_file", "arguments": {"file_path": "/test.txt"}}],
            []  # Empty on second iteration
        ]

        mock_describe.return_value = "Read file /test.txt"
        mock_preview.return_value = False  # Not a file modification tool
        mock_confirm.return_value = True
        mock_execute.return_value = "File contents"

        client.run_chat()

        # Verify custom tool was executed once
        mock_execute.assert_called_once_with("read_file", {"file_path": "/test.txt"})


class TestTerminalTools:
    """Test TERMINAL_TOOLS constant."""

    def test_terminal_tools_set(self):
        """Test that TERMINAL_TOOLS contains expected tools."""
        expected = {"create_task", "list_tasks", "show_task", "implement_task", "implement_all_tasks"}
        assert client.TERMINAL_TOOLS == expected

    def test_terminal_tools_is_set(self):
        """Test that TERMINAL_TOOLS is a set for O(1) lookup."""
        assert isinstance(client.TERMINAL_TOOLS, set)


class TestSystemPrompt:
    """Test SYSTEM_PROMPT constant."""

    def test_system_prompt_exists(self):
        """Test that SYSTEM_PROMPT is defined."""
        assert hasattr(client, "SYSTEM_PROMPT")
        assert isinstance(client.SYSTEM_PROMPT, str)
        assert len(client.SYSTEM_PROMPT) > 0

    def test_system_prompt_contains_guidelines(self):
        """Test that SYSTEM_PROMPT contains expected guidelines."""
        assert "Autonomous Software Engineer" in client.SYSTEM_PROMPT
        assert "File System" in client.SYSTEM_PROMPT
        assert "Command Window" in client.SYSTEM_PROMPT
        assert "Be Efficient" in client.SYSTEM_PROMPT
