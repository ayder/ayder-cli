"""Tests for client.py module."""

import pytest
from unittest.mock import Mock, patch, MagicMock, call
import json

from ayder_cli import client
from ayder_cli.client import ChatSession, Agent
from ayder_cli.core.config import Config
from ayder_cli.services.tools.executor import ToolExecutor, TERMINAL_TOOLS

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
        assert session.state == {
            "verbose": False,
            "permissions": set(),
            "iterations": 50,
        }
        assert session.session is None

    def test_session_initialization_with_options(self):
        """Test ChatSession initialization with permissions and iterations."""
        config = Config(
            base_url="http://test.com",
            api_key="test-key",
            model="test-model",
            num_ctx=4096,
            verbose=True
        )
        perms = {"read", "write"}
        session = ChatSession(config, "prompt", permissions=perms, iterations=5)
        
        assert session.state["permissions"] == perms
        assert session.state["iterations"] == 5
        assert session.state["verbose"] is True

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
    def test_session_get_input_default_mode_prompt(self, mock_prompt_session):
        """Verify default mode shows cyan '❯' prompt."""
        config = Config(
            base_url="http://test.com",
            api_key="test-key",
            model="test-model",
            num_ctx=4096,
            verbose=False
        )
        session = ChatSession(config, "prompt")
        session.state["mode"] = "default"  # Explicitly set default mode
        
        mock_prompt_instance = Mock()
        mock_prompt_instance.prompt.return_value = "test input"
        session.session = mock_prompt_instance
        
        result = session.get_input()
        
        # Check that prompt() was called with cyan ❯
        call_args = mock_prompt_instance.prompt.call_args
        prompt_text = str(call_args[0][0])
        assert "❯" in prompt_text
        # Check for escaped version (\x1b) as it appears in ANSI object repr
        assert "\\x1b[1;36m" in prompt_text or "\x1b[1;36m" in prompt_text  # Cyan color code
        assert result == "test input"


class TestAgent:
    """Test Agent class."""

    def test_agent_initialization(self):
        """Test Agent initialization."""
        mock_llm = Mock()
        config = Config(
            base_url="http://test.com",
            api_key="test-key",
            model="test-model",
            num_ctx=4096,
            verbose=False
        )
        session = ChatSession(config, "prompt")
        mock_executor = Mock()
        
        agent = Agent(mock_llm, mock_executor, session)
        
        assert agent.llm == mock_llm
        assert agent.tools == mock_executor
        assert agent.session == session

    def test_agent_chat_simple_response(self):
        """Test agent chat with simple text response returns content."""
        mock_llm = Mock()
        config = Config(
            base_url="http://test.com",
            api_key="test-key",
            model="test-model",
            num_ctx=4096,
            verbose=False
        )
        session = ChatSession(config, "prompt")

        # Mock ToolExecutor and its registry
        mock_executor = Mock()
        mock_registry = Mock()
        mock_registry.get_schemas.return_value = []
        mock_executor.tool_registry = mock_registry

        agent = Agent(mock_llm, mock_executor, session)

        # Mock API response
        mock_message = Mock()
        mock_message.content = "Hello there"
        mock_message.tool_calls = None

        mock_choice = Mock()
        mock_choice.message = mock_message

        mock_response = Mock()
        mock_response.choices = [mock_choice]

        mock_llm.chat.return_value = mock_response

        result = agent.chat("hello")

        assert result == "Hello there"
        # Both user and assistant messages should be added
        assert len(session.messages) == 2
        assert session.messages[0]["role"] == "user"
        assert session.messages[0]["content"] == "hello"
        assert session.messages[1]["role"] == "assistant"
        assert session.messages[1]["content"] == "Hello there"

    def test_agent_chat_delegates_to_executor(self):
        """Test agent delegates tool calls to ToolExecutor and returns None."""
        mock_llm = Mock()
        config = Config(
            base_url="http://test.com",
            api_key="test-key",
            model="test-model",
            num_ctx=4096,
            verbose=False
        )
        session = ChatSession(config, "prompt", iterations=1)

        # Mock ToolExecutor
        mock_executor = Mock()
        mock_registry = Mock()
        mock_registry.get_schemas.return_value = []
        mock_executor.tool_registry = mock_registry

        # Setup executor behavior
        mock_executor.execute_tool_calls.return_value = False

        agent = Agent(mock_llm, mock_executor, session)

        # Mock API response with tool call
        mock_tool_call = Mock()
        mock_message = Mock()
        mock_message.content = None
        mock_message.tool_calls = [mock_tool_call]

        mock_choice = Mock()
        mock_choice.message = mock_message

        mock_response = Mock()
        mock_response.choices = [mock_choice]

        mock_llm.chat.return_value = mock_response

        result = agent.chat("do something")

        assert result is None
        # Check delegation
        mock_executor.execute_tool_calls.assert_called_once()

    @patch("ayder_cli.client.parse_custom_tool_calls")
    def test_agent_chat_delegates_custom_calls(self, mock_parse):
        """Test agent delegates custom tool calls to ToolExecutor and returns None."""
        mock_llm = Mock()
        config = Config(
            base_url="http://test.com",
            api_key="test-key",
            model="test-model",
            num_ctx=4096,
            verbose=False
        )
        session = ChatSession(config, "prompt", iterations=1)

        # Mock ToolExecutor
        mock_executor = Mock()
        mock_registry = Mock()
        mock_registry.get_schemas.return_value = []
        mock_executor.tool_registry = mock_registry

        # Setup executor behavior
        mock_executor.execute_custom_calls.return_value = False

        agent = Agent(mock_llm, mock_executor, session)

        # Mock API response with custom call content
        mock_message = Mock()
        mock_message.content = "<function_call>..."
        mock_message.tool_calls = None

        mock_choice = Mock()
        mock_choice.message = mock_message

        mock_response = Mock()
        mock_response.choices = [mock_choice]

        mock_llm.chat.return_value = mock_response

        # Mock parser
        custom_call = {"name": "test_tool", "arguments": {}}
        mock_parse.return_value = [custom_call]

        result = agent.chat("do something")

        assert result is None
        # Check delegation
        mock_executor.execute_custom_calls.assert_called_once()

    def test_agent_stops_on_terminal_signal(self):
        """Test agent loop breaks when executor returns True, returns None."""
        mock_llm = Mock()
        config = Config(
            base_url="http://test.com",
            api_key="test-key",
            model="test-model",
            num_ctx=4096,
            verbose=False
        )
        session = ChatSession(config, "prompt")

        # Mock ToolExecutor
        mock_executor = Mock()
        mock_registry = Mock()
        mock_registry.get_schemas.return_value = []
        mock_executor.tool_registry = mock_registry

        # Setup executor behavior - return True (terminal)
        mock_executor.execute_tool_calls.return_value = True

        agent = Agent(mock_llm, mock_executor, session)

        # Mock API response with tool call
        mock_tool_call = Mock()
        mock_message = Mock()
        mock_message.content = None
        mock_message.tool_calls = [mock_tool_call]

        mock_choice = Mock()
        mock_choice.message = mock_message

        mock_response = Mock()
        mock_response.choices = [mock_choice]

        mock_llm.chat.return_value = mock_response

        result = agent.chat("do something")

        assert result is None
        # Should have called LLM only once despite default max_iterations=10
        assert mock_llm.chat.call_count == 1

    def test_agent_chat_error_propagates(self):
        """Test that errors from LLM calls propagate as exceptions."""
        mock_llm = Mock()
        mock_llm.chat.side_effect = RuntimeError("LLM connection failed")
        config = Config(
            base_url="http://test.com",
            api_key="test-key",
            model="test-model",
            num_ctx=4096,
            verbose=False
        )
        session = ChatSession(config, "prompt")

        mock_executor = Mock()
        mock_registry = Mock()
        mock_registry.get_schemas.return_value = []
        mock_executor.tool_registry = mock_registry

        agent = Agent(mock_llm, mock_executor, session)

        with pytest.raises(RuntimeError, match="LLM connection failed"):
            agent.chat("hello")

    def test_agent_chat_returns_none_for_empty_response(self):
        """Test agent returns None when LLM gives empty content and no tools."""
        mock_llm = Mock()
        config = Config(
            base_url="http://test.com",
            api_key="test-key",
            model="test-model",
            num_ctx=4096,
            verbose=False
        )
        session = ChatSession(config, "prompt")

        mock_executor = Mock()
        mock_registry = Mock()
        mock_registry.get_schemas.return_value = []
        mock_executor.tool_registry = mock_registry

        agent = Agent(mock_llm, mock_executor, session)

        # Mock API response with empty content and no tools
        mock_message = Mock()
        mock_message.content = None
        mock_message.tool_calls = None

        mock_choice = Mock()
        mock_choice.message = mock_message

        mock_response = Mock()
        mock_response.choices = [mock_choice]

        mock_llm.chat.return_value = mock_response

        result = agent.chat("hello")

        assert result is None

    def test_agent_chat_uses_append_raw(self):
        """Test that tool messages use append_raw instead of direct list append."""
        mock_llm = Mock()
        config = Config(
            base_url="http://test.com",
            api_key="test-key",
            model="test-model",
            num_ctx=4096,
            verbose=False
        )
        session = ChatSession(config, "prompt", iterations=1)

        mock_executor = Mock()
        mock_registry = Mock()
        mock_registry.get_schemas.return_value = []
        mock_executor.tool_registry = mock_registry
        mock_executor.execute_tool_calls.return_value = False

        agent = Agent(mock_llm, mock_executor, session)

        # Mock API response with tool call
        mock_tool_call = Mock()
        mock_message = Mock()
        mock_message.content = None
        mock_message.tool_calls = [mock_tool_call]

        mock_choice = Mock()
        mock_choice.message = mock_message

        mock_response = Mock()
        mock_response.choices = [mock_choice]

        mock_llm.chat.return_value = mock_response

        # Spy on append_raw
        with patch.object(session, "append_raw", wraps=session.append_raw) as spy:
            agent.chat("do something")
            spy.assert_called_once_with(mock_message)

    def test_agent_chat_uses_overridden_model(self):
        """Test that Agent uses the model from session state if overridden."""
        mock_llm = Mock()
        config = Config(
            base_url="http://test.com",
            api_key="test-key",
            model="original-model",
            num_ctx=4096,
            verbose=False
        )
        session = ChatSession(config, "prompt")
        session.state["model"] = "overridden-model"

        # Mock ToolExecutor and its registry
        mock_executor = Mock()
        mock_registry = Mock()
        mock_registry.get_schemas.return_value = []
        mock_executor.tool_registry = mock_registry

        agent = Agent(mock_llm, mock_executor, session)

        # Mock API response
        mock_message = Mock()
        mock_message.content = "Response"
        mock_message.tool_calls = None
        mock_choice = Mock()
        mock_choice.message = mock_message
        mock_response = Mock()
        mock_response.choices = [mock_choice]
        mock_llm.chat.return_value = mock_response

        agent.chat("hello")

        # Verify chat was called with overridden-model
        mock_llm.chat.assert_called_once()
        args, kwargs = mock_llm.chat.call_args
        assert kwargs["model"] == "overridden-model"

    def test_session_append_raw(self):
        """Test ChatSession.append_raw preserves raw message objects."""
        config = Config(
            base_url="http://test.com",
            api_key="test-key",
            model="test-model",
            num_ctx=4096,
            verbose=False
        )
        session = ChatSession(config, "prompt")

        # Simulate an OpenAI message object with tool_calls
        raw_msg = Mock()
        raw_msg.role = "assistant"
        raw_msg.content = None
        raw_msg.tool_calls = [Mock()]

        session.append_raw(raw_msg)

        assert len(session.messages) == 1
        assert session.messages[0] is raw_msg  # Same object, not a dict copy


class TestAgentIterationFeedback:
    """Tests for verbose iteration display and max iterations warning."""

    def _make_tool_response(self):
        """Create a mock LLM response that triggers a tool call."""
        mock_tool_call = Mock()
        mock_tool_call.function.name = "read_file"
        mock_tool_call.function.arguments = '{"file_path": "test.txt"}'
        mock_tool_call.id = "call_1"

        mock_message = Mock()
        mock_message.content = None
        mock_message.tool_calls = [mock_tool_call]

        mock_choice = Mock()
        mock_choice.message = mock_message

        mock_response = Mock()
        mock_response.choices = [mock_choice]
        return mock_response

    def test_max_iterations_warning_shown(self):
        """Test that a warning is displayed when max iterations are exhausted."""
        mock_llm = Mock()
        config = Config(
            base_url="http://test.com",
            api_key="test-key",
            model="test-model",
            num_ctx=4096,
            verbose=False,
        )
        session = ChatSession(config, "prompt", iterations=2)

        mock_executor = Mock()
        mock_registry = Mock()
        mock_registry.get_schemas.return_value = []
        mock_executor.tool_registry = mock_registry
        mock_executor.execute_tool_calls.return_value = False  # not terminal

        mock_llm.chat.return_value = self._make_tool_response()

        agent = Agent(mock_llm, mock_executor, session)

        with patch("ayder_cli.ui.draw_box") as mock_draw_box:
            result = agent.chat("do something")

        assert result is None
        # Should have called LLM exactly 2 times (max_iterations=2)
        assert mock_llm.chat.call_count == 2
        # Warning should be shown
        mock_draw_box.assert_called_once()
        assert "Reached maximum iterations" in mock_draw_box.call_args[0][0]

    def test_verbose_iteration_counter_shown(self):
        """Test that iteration counter is shown in verbose mode."""
        mock_llm = Mock()
        config = Config(
            base_url="http://test.com",
            api_key="test-key",
            model="test-model",
            num_ctx=4096,
            verbose=True,
        )
        session = ChatSession(config, "prompt", iterations=2)
        session.state["verbose"] = True

        mock_executor = Mock()
        mock_registry = Mock()
        mock_registry.get_schemas.return_value = []
        mock_executor.tool_registry = mock_registry
        mock_executor.execute_tool_calls.return_value = False

        mock_llm.chat.return_value = self._make_tool_response()

        agent = Agent(mock_llm, mock_executor, session)

        with patch("ayder_cli.ui.draw_box") as mock_draw_box:
            agent.chat("do something")

        # Should have 2 verbose calls + 1 warning = 3
        calls = [call[0][0] for call in mock_draw_box.call_args_list]
        assert any("Iteration 1/2" in c for c in calls)
        assert any("Iteration 2/2" in c for c in calls)

    def test_no_warning_when_iterations_not_exhausted(self):
        """Test that no warning is shown when agent finishes before limit."""
        mock_llm = Mock()
        config = Config(
            base_url="http://test.com",
            api_key="test-key",
            model="test-model",
            num_ctx=4096,
            verbose=False,
        )
        session = ChatSession(config, "prompt", iterations=50)

        mock_message = Mock()
        mock_message.content = "Here is the answer"
        mock_message.tool_calls = None

        mock_choice = Mock()
        mock_choice.message = mock_message

        mock_response = Mock()
        mock_response.choices = [mock_choice]

        mock_llm.chat.return_value = mock_response

        mock_executor = Mock()
        mock_registry = Mock()
        mock_registry.get_schemas.return_value = []
        mock_executor.tool_registry = mock_registry

        agent = Agent(mock_llm, mock_executor, session)

        with patch("ayder_cli.ui.draw_box") as mock_draw_box:
            result = agent.chat("hello")

        assert result == "Here is the answer"
        mock_draw_box.assert_not_called()

