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


class TestChatSessionRenderHistory:
    """Test ChatSession.render_history() method."""

    def test_render_history(self, capsys):
        """Test render_history outputs message history."""
        config = Config(
            base_url="http://test.com",
            api_key="test-key",
            model="test-model",
            num_ctx=4096,
            verbose=False
        )
        session = ChatSession(config, "prompt")
        session.messages = [
            {"role": "system", "content": "system message here"},
            {"role": "user", "content": "user message here"},
            {"role": "assistant", "content": "assistant message here"}
        ]
        
        session.render_history()
        
        captured = capsys.readouterr()
        assert "[system] system message here" in captured.out
        assert "[user] user message here" in captured.out
        assert "[assistant] assistant message here" in captured.out

    def test_render_history_truncates_long_content(self, capsys):
        """Test render_history truncates content over 100 chars."""
        config = Config(
            base_url="http://test.com",
            api_key="test-key",
            model="test-model",
            num_ctx=4096,
            verbose=False
        )
        session = ChatSession(config, "prompt")
        long_content = "x" * 150
        session.messages = [{"role": "user", "content": long_content}]
        
        session.render_history()
        
        captured = capsys.readouterr()
        assert "[user]" in captured.out
        assert "..." in captured.out


class TestChatSessionStartWithInitialMessage:
    """Test ChatSession.start() with different initial messages."""

    @patch("ayder_cli.client.print_welcome_banner")
    @patch("ayder_cli.client.PromptSession")
    def test_session_start_with_config_model(self, mock_prompt_session, mock_banner):
        """Test session start uses model from config."""
        config = Config(
            base_url="http://test.com",
            api_key="test-key",
            model="custom-model:latest",
            num_ctx=4096,
            verbose=False
        )
        session = ChatSession(config, "system prompt")
        
        session.start()
        
        # Check banner was called with correct model name
        mock_banner.assert_called_once()
        call_args = mock_banner.call_args
        assert call_args[0][0] == "custom-model:latest"

    @patch("ayder_cli.client.print_welcome_banner")
    @patch("ayder_cli.client.PromptSession")
    def test_session_start_config_without_model(self, mock_prompt_session, mock_banner):
        """Test session start when config has no model attribute."""
        config = Mock()
        del config.model  # Ensure no model attribute
        config.verbose = False
        
        session = ChatSession(config, "system prompt")
        session.start()
        
        # Should use default model name
        mock_banner.assert_called_once()
        call_args = mock_banner.call_args
        assert call_args[0][0] == "qwen3-coder:latest"


class TestAgentChatWithDictConfig:
    """Test Agent.chat() with dict config instead of Config object."""

    @patch("ayder_cli.client.print_running")
    @patch("ayder_cli.client.print_assistant_message")
    def test_agent_chat_with_dict_config(self, mock_print_assistant, mock_print_running):
        """Test agent chat with dict config uses dict values."""
        mock_client = Mock()
        config_dict = {
            "model": "dict-model:latest",
            "num_ctx": 8192
        }
        session = ChatSession(config_dict, "prompt")
        agent = Agent(mock_client, config_dict, session)
        
        # Mock API response
        mock_message = Mock()
        mock_message.content = "Hello from dict config"
        mock_message.tool_calls = None
        
        mock_choice = Mock()
        mock_choice.message = mock_message
        
        mock_response = Mock()
        mock_response.choices = [mock_choice]
        
        mock_client.chat.completions.create.return_value = mock_response
        
        agent.chat("hello")
        
        # Verify the API was called with dict config values
        call_kwargs = mock_client.chat.completions.create.call_args
        assert call_kwargs[1]["model"] == "dict-model:latest"
        assert call_kwargs[1]["extra_body"] == {"options": {"num_ctx": 8192}}


class TestAgentChatToolCallResponse:
    """Test Agent.chat() handling of tool_call responses."""

    @patch("ayder_cli.client.print_running")
    @patch("ayder_cli.client.fs_tools")
    def test_agent_chat_with_tool_calls(self, mock_fs_tools, mock_print_running):
        """Test agent handles OpenAI-style tool calls."""
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
        
        # Mock API response with tool calls
        mock_tool_call = Mock()
        mock_tool_call.id = "call_123"
        mock_tool_call.function.name = "list_files"
        mock_tool_call.function.arguments = '{"directory": "."}'
        
        mock_message = Mock()
        mock_message.content = None
        mock_message.tool_calls = [mock_tool_call]
        
        mock_choice = Mock()
        mock_choice.message = mock_message
        
        mock_response = Mock()
        mock_response.choices = [mock_choice]
        
        mock_client.chat.completions.create.return_value = mock_response
        
        # Mock fs_tools
        mock_fs_tools.normalize_tool_arguments.return_value = {"directory": "."}
        mock_fs_tools.validate_tool_call.return_value = (True, None)
        mock_fs_tools.execute_tool_call.return_value = "file1.txt\nfile2.txt"
        mock_fs_tools.tools_schema = []
        
        with patch("ayder_cli.client.confirm_tool_call", return_value=True):
            with patch("ayder_cli.client.describe_tool_action", return_value="List files"):
                with patch("ayder_cli.client.print_tool_result"):
                    agent.chat("list files")
        
        # Verify tool call result was added to messages
        assert any(msg.get("role") == "tool" for msg in session.messages)

    @patch("ayder_cli.client.print_running")
    @patch("ayder_cli.client.fs_tools")
    def test_agent_chat_with_terminal_tool(self, mock_fs_tools, mock_print_running):
        """Test agent stops after terminal tool execution."""
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
        
        # Mock API response with terminal tool (create_task)
        mock_tool_call = Mock()
        mock_tool_call.id = "call_123"
        mock_tool_call.function.name = "create_task"
        mock_tool_call.function.arguments = '{"title": "Test Task"}'
        
        mock_message = Mock()
        mock_message.content = None
        mock_message.tool_calls = [mock_tool_call]
        
        mock_choice = Mock()
        mock_choice.message = mock_message
        
        mock_response = Mock()
        mock_response.choices = [mock_choice]
        
        mock_client.chat.completions.create.return_value = mock_response
        
        # Mock fs_tools
        mock_fs_tools.normalize_tool_arguments.return_value = {"title": "Test Task"}
        mock_fs_tools.validate_tool_call.return_value = (True, None)
        mock_fs_tools.execute_tool_call.return_value = "Task created"
        mock_fs_tools.tools_schema = []
        
        with patch("ayder_cli.client.confirm_tool_call", return_value=True):
            with patch("ayder_cli.client.describe_tool_action", return_value="Create task"):
                with patch("ayder_cli.client.print_tool_result"):
                    agent.chat("create a task")
        
        # Should have tool result in messages
        assert any(msg.get("role") == "tool" for msg in session.messages)


class TestAgentChatParserErrors:
    """Test Agent.chat() handling of parser errors."""

    @patch("ayder_cli.client.print_running")
    @patch("ayder_cli.client.parse_custom_tool_calls")
    def test_agent_chat_with_parser_error(self, mock_parse, mock_print_running):
        """Test agent handles parser errors in custom tool calls."""
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
        
        # Mock API response with content but no tool_calls
        mock_message = Mock()
        mock_message.content = "<function_call>invalid</function_call>"
        mock_message.tool_calls = None
        
        mock_choice = Mock()
        mock_choice.message = mock_message
        
        mock_response = Mock()
        mock_response.choices = [mock_choice]
        
        mock_client.chat.completions.create.return_value = mock_response
        mock_fs_tools = Mock()
        mock_fs_tools.tools_schema = []
        
        # Mock parser to return error
        mock_parse.return_value = [{"error": "Invalid XML format"}]
        
        with patch("ayder_cli.client.fs_tools", mock_fs_tools):
            agent.chat("test")
        
        # Verify error message was added
        assert any("Tool parsing error" in msg.get("content", "") for msg in session.messages)


class TestAgentHandleToolCallEdgeCases:
    """Test Agent._handle_tool_call() edge cases."""

    @patch("ayder_cli.client.fs_tools")
    @patch("ayder_cli.client.describe_tool_action")
    @patch("ayder_cli.client.print_tool_result")
    def test_handle_tool_call_with_invalid_tool(self, mock_print_result, mock_describe, mock_fs_tools):
        """Test handling of invalid tool call."""
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
        
        mock_tool_call = Mock()
        mock_tool_call.id = "call_123"
        mock_tool_call.function.name = "invalid_tool"
        mock_tool_call.function.arguments = '{}'
        
        # Mock validation to fail
        mock_fs_tools.normalize_tool_arguments.return_value = {}
        mock_fs_tools.validate_tool_call.return_value = (False, "Unknown tool: invalid_tool")
        
        result = agent._handle_tool_call(mock_tool_call)
        
        # Should return validation error
        assert result is not None
        assert result["role"] == "tool"
        assert "Validation Error" in result["content"]

    @patch("ayder_cli.client.fs_tools")
    @patch("ayder_cli.client.describe_tool_action")
    def test_handle_tool_call_with_dict_arguments(self, mock_describe, mock_fs_tools):
        """Test handling tool call when arguments is already a dict."""
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
        
        mock_tool_call = Mock()
        mock_tool_call.id = "call_123"
        mock_tool_call.function.name = "list_files"
        mock_tool_call.function.arguments = {"directory": "."}  # Already a dict
        
        mock_fs_tools.normalize_tool_arguments.return_value = {"directory": "."}
        mock_fs_tools.validate_tool_call.return_value = (True, None)
        mock_fs_tools.execute_tool_call.return_value = "file1.txt"
        
        mock_describe.return_value = "List files"
        
        with patch("ayder_cli.client.confirm_tool_call", return_value=True):
            with patch("ayder_cli.client.print_tool_result"):
                result = agent._handle_tool_call(mock_tool_call)
        
        assert result is not None
        assert result["role"] == "tool"

    @patch("ayder_cli.client.fs_tools")
    @patch("ayder_cli.client.describe_tool_action")
    @patch("ayder_cli.client.confirm_with_diff")
    @patch("ayder_cli.client.prepare_new_content")
    @patch("ayder_cli.client.print_file_content")
    def test_handle_tool_call_write_file_with_verbose(
        self, mock_print_file, mock_prepare, mock_confirm_diff, mock_describe, mock_fs_tools
    ):
        """Test verbose mode output for write_file."""
        mock_client = Mock()
        config = Config(
            base_url="http://test.com",
            api_key="test-key",
            model="test-model",
            num_ctx=4096,
            verbose=True
        )
        session = ChatSession(config, "prompt")
        session.state["verbose"] = True
        agent = Agent(mock_client, config, session)
        
        mock_tool_call = Mock()
        mock_tool_call.id = "call_123"
        mock_tool_call.function.name = "write_file"
        mock_tool_call.function.arguments = '{"file_path": "test.txt", "content": "hello"}'
        
        mock_fs_tools.normalize_tool_arguments.return_value = {"file_path": "test.txt", "content": "hello"}
        mock_fs_tools.validate_tool_call.return_value = (True, None)
        mock_fs_tools.execute_tool_call.return_value = "Successfully wrote"
        
        mock_describe.return_value = "Write file"
        mock_prepare.return_value = "hello"
        mock_confirm_diff.return_value = True
        
        with patch("ayder_cli.client.print_tool_result"):
            result = agent._handle_tool_call(mock_tool_call)
        
        assert result is not None
        mock_print_file.assert_called_once_with("test.txt")


class TestAgentExecuteToolLoop:
    """Test Agent._execute_tool_loop() method."""

    def test_execute_tool_loop_with_declined_tool(self):
        """Test that declined tool stops the loop."""
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
        
        # Mock a tool call that will be declined (returns None)
        mock_tool_call = Mock()
        mock_tool_call.id = "call_123"
        mock_tool_call.function.name = "list_files"
        mock_tool_call.function.arguments = '{}'
        
        with patch.object(agent, "_handle_tool_call", return_value=None):
            result = agent._execute_tool_loop([mock_tool_call])
        
        # Should return True when tool is declined
        assert result is True

    def test_execute_tool_loop_with_multiple_tools(self):
        """Test executing multiple tool calls."""
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
        
        mock_tool_call1 = Mock()
        mock_tool_call1.id = "call_1"
        mock_tool_call1.function.name = "list_files"
        mock_tool_call1.function.arguments = '{}'
        
        mock_tool_call2 = Mock()
        mock_tool_call2.id = "call_2"
        mock_tool_call2.function.name = "read_file"
        mock_tool_call2.function.arguments = '{"file_path": "test.txt"}'
        
        result_msg1 = {"role": "tool", "tool_call_id": "call_1", "content": "files"}
        result_msg2 = {"role": "tool", "tool_call_id": "call_2", "content": "content"}
        
        with patch.object(agent, "_handle_tool_call", side_effect=[result_msg1, result_msg2]):
            result = agent._execute_tool_loop([mock_tool_call1, mock_tool_call2])
        
        # Both tools executed, no terminal tool
        assert result is False
        # Both results should be in session messages
        assert len(session.messages) == 2


class TestAgentHandleCustomCalls:
    """Test Agent._handle_custom_calls() method."""

    @patch("ayder_cli.client.fs_tools")
    @patch("ayder_cli.client.describe_tool_action")
    @patch("ayder_cli.client.print_tool_result")
    def test_handle_custom_calls_validation_error(self, mock_print_result, mock_describe, mock_fs_tools):
        """Test validation error in custom calls stops execution."""
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
        
        custom_calls = [{"name": "invalid_tool", "arguments": {}}]
        
        mock_fs_tools.normalize_tool_arguments.return_value = {}
        mock_fs_tools.validate_tool_call.return_value = (False, "Invalid tool")
        
        result = agent._handle_custom_calls(custom_calls)
        
        # Should return True on validation error
        assert result is True
        # Error message should be added to session
        assert any("Validation Error" in msg.get("content", "") for msg in session.messages)

    @patch("ayder_cli.client.fs_tools")
    @patch("ayder_cli.client.describe_tool_action")
    @patch("ayder_cli.client.print_tool_skipped")
    def test_handle_custom_calls_declined(self, mock_print_skipped, mock_describe, mock_fs_tools):
        """Test declined custom call stops execution."""
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
        
        custom_calls = [{"name": "list_files", "arguments": {"directory": "."}}]
        
        mock_fs_tools.normalize_tool_arguments.return_value = {"directory": "."}
        mock_fs_tools.validate_tool_call.return_value = (True, None)
        mock_describe.return_value = "List files"
        
        with patch("ayder_cli.client.confirm_tool_call", return_value=False):
            result = agent._handle_custom_calls(custom_calls)
        
        # Should return True when declined
        assert result is True
        mock_print_skipped.assert_called_once()

    @patch("ayder_cli.client.fs_tools")
    @patch("ayder_cli.client.describe_tool_action")
    @patch("ayder_cli.client.confirm_tool_call")
    @patch("ayder_cli.client.print_tool_result")
    def test_handle_custom_calls_with_terminal_tool(
        self, mock_print_result, mock_confirm, mock_describe, mock_fs_tools
    ):
        """Test terminal tool in custom calls returns True."""
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
        
        custom_calls = [{"name": "create_task", "arguments": {"title": "Test"}}]
        
        mock_fs_tools.normalize_tool_arguments.return_value = {"title": "Test"}
        mock_fs_tools.validate_tool_call.return_value = (True, None)
        mock_fs_tools.execute_tool_call.return_value = "Task created"
        mock_describe.return_value = "Create task"
        mock_confirm.return_value = True
        
        result = agent._handle_custom_calls(custom_calls)
        
        # Should return True for terminal tool
        assert result is True
        # Result should be added as user message
        assert any("Tool 'create_task' execution result" in msg.get("content", "") for msg in session.messages)


class TestRunChatEdgeCases:
    """Test run_chat() edge cases."""

    @patch("ayder_cli.client.load_config")
    @patch("ayder_cli.client.OpenAI")
    @patch("ayder_cli.client.PromptSession")
    @patch("ayder_cli.client.print_welcome_banner")
    @patch("ayder_cli.client.fs_tools")
    def test_run_chat_with_dict_config(
        self, mock_fs_tools, mock_banner, mock_session, mock_openai, mock_config
    ):
        """Test run_chat with dict config instead of Config object."""
        mock_config.return_value = {
            "base_url": "http://test.com",
            "api_key": "test-key",
            "model": "test-model",
            "num_ctx": 4096,
            "verbose": False
        }
        mock_fs_tools.get_project_structure.return_value = "test structure"
        mock_fs_tools.tools_schema = []
        
        mock_instance = Mock()
        mock_instance.prompt.side_effect = ["exit"]
        mock_session.return_value = mock_instance
        
        client.run_chat()
        
        # Verify OpenAI client was created with dict values
        mock_openai.assert_called_once_with(base_url="http://test.com", api_key="test-key")

    @patch("ayder_cli.client.load_config")
    @patch("ayder_cli.client.OpenAI")
    @patch("ayder_cli.client.PromptSession")
    @patch("ayder_cli.client.print_welcome_banner")
    @patch("ayder_cli.client.fs_tools")
    def test_run_chat_project_structure_exception(
        self, mock_fs_tools, mock_banner, mock_session, mock_openai, mock_config
    ):
        """Test run_chat handles exception in get_project_structure."""
        mock_config.return_value = Config(
            base_url="http://test.com",
            api_key="test-key",
            model="test-model",
            num_ctx=4096,
            verbose=False
        )
        # Make get_project_structure raise an exception
        mock_fs_tools.get_project_structure.side_effect = Exception("Permission denied")
        mock_fs_tools.tools_schema = []
        
        mock_instance = Mock()
        mock_instance.prompt.side_effect = ["exit"]
        mock_session.return_value = mock_instance
        
        # Should not raise exception
        client.run_chat()
        
        # Verify banner was still printed
        mock_banner.assert_called_once()


class TestRunChatMainEntry:
    """Test __main__ entry point."""

    @patch("ayder_cli.client.run_chat")
    def test_main_entry_point(self, mock_run_chat):
        """Test __main__ block calls run_chat()."""
        # We can't directly test __main__ block, but we can verify run_chat exists
        assert hasattr(client, "run_chat")
        assert callable(client.run_chat)


class TestAgentChatCustomCallsBranch:
    """Test Agent.chat() with custom_calls branch (lines 193-195)."""

    @patch("ayder_cli.client.print_running")
    @patch("ayder_cli.client.fs_tools")
    @patch("ayder_cli.client.parse_custom_tool_calls")
    def test_chat_with_custom_calls_terminal_tool(
        self, mock_parse, mock_fs_tools, mock_print_running
    ):
        """Test chat breaks loop when custom_calls hits terminal tool (lines 193-195)."""
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
        
        # First API response has content that parses to custom tool call
        mock_message = Mock()
        mock_message.content = "<function_call>create_task...</function_call>"
        mock_message.tool_calls = None
        
        mock_choice = Mock()
        mock_choice.message = mock_message
        
        mock_response = Mock()
        mock_response.choices = [mock_choice]
        
        mock_client.chat.completions.create.return_value = mock_response
        mock_fs_tools.tools_schema = []
        
        # Parse returns a terminal tool call
        mock_parse.return_value = [{"name": "create_task", "arguments": {"title": "Test"}}]
        
        # Mock fs_tools for validation and execution
        mock_fs_tools.normalize_tool_arguments.return_value = {"title": "Test"}
        mock_fs_tools.validate_tool_call.return_value = (True, None)
        mock_fs_tools.execute_tool_call.return_value = "Task created"
        
        with patch("ayder_cli.client.describe_tool_action", return_value="Create task"):
            with patch("ayder_cli.client.confirm_tool_call", return_value=True):
                with patch("ayder_cli.client.print_tool_result"):
                    agent.chat("create a task")
        
        # Verify the custom call was processed - check for dict messages with content key
        found_result = False
        for msg in session.messages:
            if isinstance(msg, dict) and "content" in msg:
                content = msg.get("content", "")
                if isinstance(content, str) and "Tool 'create_task' execution result" in content:
                    found_result = True
                    break
        assert found_result, "Expected tool execution result message not found"


class TestAgentHandleCustomCallsFileModifying:
    """Test _handle_custom_calls with file-modifying tools (lines 304-306)."""

    @patch("ayder_cli.client.fs_tools")
    @patch("ayder_cli.client.describe_tool_action")
    @patch("ayder_cli.client.confirm_with_diff")
    @patch("ayder_cli.client.prepare_new_content")
    @patch("ayder_cli.client.print_tool_result")
    def test_handle_custom_calls_write_file_with_diff(
        self, mock_print_result, mock_prepare, mock_confirm_diff, mock_describe, mock_fs_tools
    ):
        """Test write_file in custom calls uses diff preview (lines 304-306)."""
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
        
        custom_calls = [{"name": "write_file", "arguments": {"file_path": "test.txt", "content": "hello"}}]
        
        mock_fs_tools.normalize_tool_arguments.return_value = {"file_path": "test.txt", "content": "hello"}
        mock_fs_tools.validate_tool_call.return_value = (True, None)
        mock_fs_tools.execute_tool_call.return_value = "Successfully wrote to file"
        mock_describe.return_value = "Write file"
        mock_prepare.return_value = "hello"
        mock_confirm_diff.return_value = True
        
        result = agent._handle_custom_calls(custom_calls)
        
        # Verify confirm_with_diff was called for write_file
        mock_confirm_diff.assert_called_once_with("test.txt", "hello", "Write file")
        assert result is False  # Not a terminal tool

    @patch("ayder_cli.client.fs_tools")
    @patch("ayder_cli.client.describe_tool_action")
    @patch("ayder_cli.client.confirm_with_diff")
    @patch("ayder_cli.client.prepare_new_content")
    @patch("ayder_cli.client.print_file_content")
    @patch("ayder_cli.client.print_tool_result")
    def test_handle_custom_calls_write_file_verbose_success(
        self, mock_print_result, mock_print_file, mock_prepare, mock_confirm_diff, mock_describe, mock_fs_tools
    ):
        """Test verbose mode prints file content on successful write (line 318)."""
        mock_client = Mock()
        config = Config(
            base_url="http://test.com",
            api_key="test-key",
            model="test-model",
            num_ctx=4096,
            verbose=True
        )
        session = ChatSession(config, "prompt")
        session.state["verbose"] = True
        agent = Agent(mock_client, config, session)
        
        custom_calls = [{"name": "write_file", "arguments": {"file_path": "test.txt", "content": "hello"}}]
        
        mock_fs_tools.normalize_tool_arguments.return_value = {"file_path": "test.txt", "content": "hello"}
        mock_fs_tools.validate_tool_call.return_value = (True, None)
        mock_fs_tools.execute_tool_call.return_value = "Successfully wrote to test.txt"
        mock_describe.return_value = "Write file"
        mock_prepare.return_value = "hello"
        mock_confirm_diff.return_value = True
        
        result = agent._handle_custom_calls(custom_calls)
        
        # Verify print_file_content was called for successful write in verbose mode
        mock_print_file.assert_called_once_with("test.txt")
        assert result is False

    @patch("ayder_cli.client.fs_tools")
    @patch("ayder_cli.client.describe_tool_action")
    @patch("ayder_cli.client.confirm_tool_call")
    @patch("ayder_cli.client.print_tool_result")
    def test_handle_custom_calls_non_terminal_non_file_tool(
        self, mock_print_result, mock_confirm, mock_describe, mock_fs_tools
    ):
        """Test non-terminal, non-file tool returns False (line 329)."""
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
        
        # list_files is not a terminal tool and not a file-modifying tool
        custom_calls = [{"name": "list_files", "arguments": {"directory": "."}}]
        
        mock_fs_tools.normalize_tool_arguments.return_value = {"directory": "."}
        mock_fs_tools.validate_tool_call.return_value = (True, None)
        mock_fs_tools.execute_tool_call.return_value = "file1.txt\nfile2.txt"
        mock_describe.return_value = "List files"
        mock_confirm.return_value = True
        
        result = agent._handle_custom_calls(custom_calls)
        
        # Should return False for non-terminal tool (line 329)
        assert result is False
        # Result message should be added
        assert any("Tool 'list_files' execution result" in msg.get("content", "") for msg in session.messages)
