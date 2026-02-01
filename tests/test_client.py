"""Tests for client.py module."""

import pytest
from unittest.mock import Mock, patch, MagicMock, call
import json

from ayder_cli import client
from ayder_cli.client import ChatSession, Agent
from ayder_cli.config import Config

class TestChatSession:
    """Test ChatSession class."""

    def test_session_initialization(self):
        """Test ChatSession initialization."""
        config = Config(
            base_url="http://test.com",
            api_key="test-key",
            model="test-model",
            num_ctx=4096,
            verbose=False
        )
        session = ChatSession(config, "test prompt")
        
        assert session.config == config
        assert session.system_prompt == "test prompt"
        assert session.messages == []
        assert session.state == {"verbose": False}
        assert session.session is None

    def test_session_add_message(self):
        """Test adding messages to history."""
        config = Config(
            base_url="http://test.com",
            api_key="test-key",
            model="test-model",
            num_ctx=4096,
            verbose=False
        )
        session = ChatSession(config, "prompt")
        
        session.add_message("user", "hello")
        assert len(session.messages) == 1
        assert session.messages[0]["role"] == "user"
        assert session.messages[0]["content"] == "hello"
        
        session.add_message("assistant", "hi there")
        assert len(session.messages) == 2
        assert session.messages[1]["role"] == "assistant"

    def test_session_add_message_with_kwargs(self):
        """Test adding message with additional fields."""
        config = Config(
            base_url="http://test.com",
            api_key="test-key",
            model="test-model",
            num_ctx=4096,
            verbose=False
        )
        session = ChatSession(config, "prompt")
        
        session.add_message("tool", "result", tool_call_id="123", name="test_tool")
        assert len(session.messages) == 1
        assert session.messages[0]["role"] == "tool"
        assert session.messages[0]["content"] == "result"
        assert session.messages[0]["tool_call_id"] == "123"
        assert session.messages[0]["name"] == "test_tool"

    def test_session_get_messages(self):
        """Test getting message history."""
        config = Config(
            base_url="http://test.com",
            api_key="test-key",
            model="test-model",
            num_ctx=4096,
            verbose=False
        )
        session = ChatSession(config, "prompt")
        
        session.add_message("user", "hello")
        session.add_message("assistant", "hi")
        
        messages = session.get_messages()
        assert len(messages) == 2
        assert messages[0]["content"] == "hello"
        assert messages[1]["content"] == "hi"

    def test_session_clear_messages_keep_system(self):
        """Test clearing messages while keeping system prompt."""
        config = Config(
            base_url="http://test.com",
            api_key="test-key",
            model="test-model",
            num_ctx=4096,
            verbose=False
        )
        session = ChatSession(config, "system prompt")
        session.messages = [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"}
        ]
        
        session.clear_messages(keep_system=True)
        assert len(session.messages) == 1
        assert session.messages[0]["role"] == "system"

    def test_session_clear_messages_all(self):
        """Test clearing all messages."""
        config = Config(
            base_url="http://test.com",
            api_key="test-key",
            model="test-model",
            num_ctx=4096,
            verbose=False
        )
        session = ChatSession(config, "system prompt")
        session.messages = [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "hello"}
        ]
        
        session.clear_messages(keep_system=False)
        assert len(session.messages) == 0

    @patch("ayder_cli.client.print_welcome_banner")
    @patch("ayder_cli.client.PromptSession")
    def test_session_start(self, mock_prompt_session, mock_banner):
        """Test session start method."""
        config = Config(
            base_url="http://test.com",
            api_key="test-key",
            model="test-model",
            num_ctx=4096,
            verbose=False
        )
        session = ChatSession(config, "system prompt")
        
        session.start()
        
        # Check messages initialized with system prompt
        assert len(session.messages) == 1
        assert session.messages[0]["role"] == "system"
        assert session.messages[0]["content"] == "system prompt"
        
        # Check prompt session created
        mock_prompt_session.assert_called_once()
        assert session.session is not None
        
        # Check banner printed
        mock_banner.assert_called_once()

    @patch("ayder_cli.client.PromptSession")
    def test_session_get_input_normal(self, mock_prompt_session):
        """Test normal user input."""
        config = Config(
            base_url="http://test.com",
            api_key="test-key",
            model="test-model",
            num_ctx=4096,
            verbose=False
        )
        session = ChatSession(config, "prompt")
        
        mock_prompt_instance = Mock()
        mock_prompt_instance.prompt.return_value = "hello"
        session.session = mock_prompt_instance
        
        result = session.get_input()
        assert result == "hello"

    @patch("ayder_cli.client.PromptSession")
    @patch("builtins.print")
    def test_session_get_input_exit(self, mock_print, mock_prompt_session):
        """Test exit command."""
        config = Config(
            base_url="http://test.com",
            api_key="test-key",
            model="test-model",
            num_ctx=4096,
            verbose=False
        )
        session = ChatSession(config, "prompt")
        
        mock_prompt_instance = Mock()
        mock_prompt_instance.prompt.return_value = "exit"
        session.session = mock_prompt_instance
        
        result = session.get_input()
        assert result is None
        mock_print.assert_called_once()

    @patch("ayder_cli.client.PromptSession")
    @patch("builtins.print")
    def test_session_get_input_empty(self, mock_print, mock_prompt_session):
        """Test empty input."""
        config = Config(
            base_url="http://test.com",
            api_key="test-key",
            model="test-model",
            num_ctx=4096,
            verbose=False
        )
        session = ChatSession(config, "prompt")
        
        mock_prompt_instance = Mock()
        mock_prompt_instance.prompt.return_value = "   "
        session.session = mock_prompt_instance
        
        result = session.get_input()
        assert result == ""


class TestAgent:
    """Test Agent class."""

    def test_agent_initialization(self):
        """Test Agent initialization."""
        mock_client = Mock()
        config = Config(
            base_url="http://test.com",
            api_key="test-key",
            model="test-model",
            num_ctx=4096,
            verbose=False
        )
        session = ChatSession(config, "prompt")
        
        agent = Agent(mock_client, config, session)
        
        assert agent.client == mock_client
        assert agent.config == config
        assert agent.session == session
        assert agent.terminal_tools == client.TERMINAL_TOOLS

    @patch("ayder_cli.client.print_running")
    @patch("ayder_cli.client.print_assistant_message")
    def test_agent_chat_simple_response(self, mock_print_assistant, mock_print_running):
        """Test agent chat with simple text response."""
        mock_client = Mock()
        config = Config(
            base_url="http://test.com",
            api_key="test-key",
            model="test-model",
            num_ctx=4096,
            verbose=False
        )
        session = ChatSession(config, "prompt")
        agent = Agent(mock_client, config, session)
        
        # Mock API response
        mock_message = Mock()
        mock_message.content = "Hello there"
        mock_message.tool_calls = None
        
        mock_choice = Mock()
        mock_choice.message = mock_message
        
        mock_response = Mock()
        mock_response.choices = [mock_choice]
        
        mock_client.chat.completions.create.return_value = mock_response
        
        agent.chat("hello")
        
        # Both user and assistant messages should be added
        assert len(session.messages) == 2
        assert session.messages[0]["role"] == "user"
        assert session.messages[0]["content"] == "hello"
        assert session.messages[1]["role"] == "assistant"
        assert session.messages[1]["content"] == "Hello there"

    @patch("ayder_cli.client.fs_tools")
    @patch("ayder_cli.client.print_running")
    @patch("ayder_cli.client.confirm_tool_call")
    @patch("ayder_cli.client.describe_tool_action")
    @patch("ayder_cli.client.print_tool_result")
    def test_agent_handle_tool_call(self, mock_print_result, mock_describe, mock_confirm, mock_print_running, mock_fs_tools):
        """Test agent handling a tool call."""
        mock_client = Mock()
        config = Config(
            base_url="http://test.com",
            api_key="test-key",
            model="test-model",
            num_ctx=4096,
            verbose=False
        )
        session = ChatSession(config, "prompt")
        agent = Agent(mock_client, config, session)
        
        # Mock tool call
        mock_tool_call = Mock()
        mock_tool_call.id = "call_123"
        mock_tool_call.function.name = "list_files"
        mock_tool_call.function.arguments = '{"directory": "."}'
        
        # Mock fs_tools
        mock_fs_tools.normalize_tool_arguments.return_value = {"directory": "."}
        mock_fs_tools.validate_tool_call.return_value = (True, None)
        mock_fs_tools.execute_tool_call.return_value = "file1.txt\nfile2.txt"
        
        mock_describe.return_value = "List files in ."
        mock_confirm.return_value = True
        
        result = agent._handle_tool_call(mock_tool_call)
        
        assert result is not None
        assert result["role"] == "tool"
        assert result["tool_call_id"] == "call_123"
        assert result["name"] == "list_files"
        assert "file1.txt" in result["content"]

    @patch("ayder_cli.client.fs_tools")
    @patch("ayder_cli.client.print_running")
    @patch("ayder_cli.client.confirm_tool_call")
    @patch("ayder_cli.client.describe_tool_action")
    @patch("ayder_cli.client.print_tool_skipped")
    def test_agent_handle_tool_call_declined(self, mock_skipped, mock_describe, mock_confirm, mock_print_running, mock_fs_tools):
        """Test agent handling a declined tool call."""
        mock_client = Mock()
        config = Config(
            base_url="http://test.com",
            api_key="test-key",
            model="test-model",
            num_ctx=4096,
            verbose=False
        )
        session = ChatSession(config, "prompt")
        agent = Agent(mock_client, config, session)
        
        # Mock tool call
        mock_tool_call = Mock()
        mock_tool_call.id = "call_123"
        mock_tool_call.function.name = "list_files"
        mock_tool_call.function.arguments = '{"directory": "."}'
        
        # Mock fs_tools
        mock_fs_tools.normalize_tool_arguments.return_value = {"directory": "."}
        mock_fs_tools.validate_tool_call.return_value = (True, None)
        
        mock_describe.return_value = "List files in ."
        mock_confirm.return_value = False  # User declines
        
        result = agent._handle_tool_call(mock_tool_call)
        
        assert result is None
        mock_skipped.assert_called_once()


class TestRunChatExitHandling:
    """Test exit command handling in run_chat()."""

    @patch("ayder_cli.client.load_config")
    @patch("ayder_cli.client.OpenAI")
    @patch("ayder_cli.client.PromptSession")
    @patch("ayder_cli.client.print_welcome_banner")
    @patch("builtins.print")
    def test_exit_command_quits(self, mock_print, mock_banner, mock_session, mock_openai, mock_config):
        """Test that 'exit' command quits the chat loop."""
        mock_config.return_value = Config(
            base_url="http://test.com",
            api_key="test-key",
            model="test-model",
            num_ctx=4096,
            verbose=False
        )
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
        mock_config.return_value = Config(
            base_url="http://test.com",
            api_key="test-key",
            model="test-model",
            num_ctx=4096,
            verbose=False
        )
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
        mock_config.return_value = Config(
            base_url="http://test.com",
            api_key="test-key",
            model="test-model",
            num_ctx=4096,
            verbose=False
        )
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
        mock_config.return_value = Config(
            base_url="http://test.com",
            api_key="test-key",
            model="test-model",
            num_ctx=4096,
            verbose=False
        )
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
        mock_config.return_value = Config(
            base_url="http://test.com",
            api_key="test-key",
            model="test-model",
            num_ctx=4096,
            verbose=False
        )
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
        mock_config.return_value = Config(
            base_url="http://test.com",
            api_key="test-key",
            model="test-model",
            num_ctx=4096,
            verbose=False
        )
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
    @patch("ayder_cli.client.fs_tools")
    @patch("builtins.print")
    def test_general_exception(self, mock_print, mock_fs_tools, mock_draw_box, mock_banner, mock_session, mock_openai, mock_config):
        """Test general exception handling shows error box."""
        mock_config.return_value = Config(
            base_url="http://test.com",
            api_key="test-key",
            model="test-model",
            num_ctx=4096,
            verbose=False
        )
        
        # Mock successful input, but make agent.chat raise an exception
        mock_instance = Mock()
        mock_instance.prompt.side_effect = ["test input", "exit"]
        mock_session.return_value = mock_instance
        
        # Mock the OpenAI client to raise an exception
        mock_openai_instance = Mock()
        mock_openai_instance.chat.completions.create.side_effect = Exception("Test error")
        mock_openai.return_value = mock_openai_instance
        
        # Mock fs_tools
        mock_fs_tools.get_project_structure.return_value = "test structure"
        mock_fs_tools.tools_schema = []
        
        client.run_chat()
        
        # Verify draw_box was called with error message
        mock_draw_box.assert_called()
        # Check that error was printed
        assert any("Test error" in str(call) for call in mock_draw_box.call_args_list)


class TestRunChatSlashCommands:
    """Test slash command handling in run_chat()."""

    @patch("ayder_cli.client.load_config")
    @patch("ayder_cli.client.OpenAI")
    @patch("ayder_cli.client.PromptSession")
    @patch("ayder_cli.client.print_welcome_banner")
    @patch("ayder_cli.client.handle_command")
    def test_slash_command_handled(self, mock_handle, mock_banner, mock_session, mock_openai, mock_config):
        """Test that slash commands call handle_command."""
        mock_config.return_value = Config(
            base_url="http://test.com",
            api_key="test-key",
            model="test-model",
            num_ctx=4096,
            verbose=False
        )
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

    def test_system_prompt_imported(self):
        """Test that SYSTEM_PROMPT is imported from prompts."""
        from ayder_cli.prompts import SYSTEM_PROMPT
        assert isinstance(SYSTEM_PROMPT, str)
        assert len(SYSTEM_PROMPT) > 0

    def test_system_prompt_contains_guidelines(self):
        """Test that SYSTEM_PROMPT contains expected guidelines."""
        from ayder_cli.prompts import SYSTEM_PROMPT
        assert "Autonomous Software Engineer" in SYSTEM_PROMPT
        assert "OPERATIONAL PRINCIPLES" in SYSTEM_PROMPT
        assert "TOOL PROTOCOL" in SYSTEM_PROMPT
        assert "CAPABILITIES" in SYSTEM_PROMPT
