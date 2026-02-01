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
        assert "OPERATIONAL PRINCIPLES" in client.SYSTEM_PROMPT
        assert "TOOL PROTOCOL" in client.SYSTEM_PROMPT
        assert "CAPABILITIES" in client.SYSTEM_PROMPT
