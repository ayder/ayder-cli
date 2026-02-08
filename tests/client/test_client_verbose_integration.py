"""Integration tests for verbose mode LLM request display."""

from unittest.mock import Mock, patch, MagicMock
from ayder_cli.client import Agent, ChatSession
from ayder_cli.core.config import Config
from ayder_cli.services.tools.executor import ToolExecutor
from ayder_cli.tools import create_default_registry
from ayder_cli.core.context import ProjectContext


class TestVerboseModeIntegration:
    """Integration tests for verbose mode displaying LLM requests."""

    def test_verbose_mode_shows_llm_requests(self):
        """Test that verbose mode displays LLM request details in agent loop."""
        # Setup mocks
        mock_llm = Mock()
        mock_response = Mock()
        mock_message = Mock()
        mock_message.content = "I'll help you with that."
        mock_message.tool_calls = None
        mock_response.choices = [Mock(message=mock_message)]
        mock_llm.chat.return_value = mock_response
        
        # Create session with verbose enabled
        config = Config(
            base_url="http://localhost:11434/v1",
            api_key="test",
            model="qwen3-coder:latest",
            num_ctx=8192,
            editor="vim",
            verbose=False
        )
        
        project_ctx = ProjectContext(".")
        registry = create_default_registry(project_ctx)
        tools = ToolExecutor(registry, project_ctx)
        
        session = ChatSession(
            config=config,
            system_prompt="Test prompt",
            permissions=set(),
            iterations=1
        )
        session.state["verbose"] = True  # Enable verbose mode
        
        agent = Agent(mock_llm, tools, session)
        
        # Execute chat
        agent.chat("Test input")
        
        # Verify LLM was called with verbose=True
        mock_llm.chat.assert_called_once()
        call_kwargs = mock_llm.chat.call_args[1]
        assert call_kwargs.get("verbose") is True

    def test_non_verbose_mode_no_llm_display(self):
        """Test that non-verbose mode does not display LLM requests."""
        # Setup mocks
        mock_llm = Mock()
        mock_response = Mock()
        mock_message = Mock()
        mock_message.content = "Response"
        mock_message.tool_calls = None
        mock_response.choices = [Mock(message=mock_message)]
        mock_llm.chat.return_value = mock_response
        
        config = Config(
            base_url="http://localhost:11434/v1",
            api_key="test",
            model="qwen3-coder:latest",
            num_ctx=8192,
            editor="vim",
            verbose=False
        )
        
        project_ctx = ProjectContext(".")
        registry = create_default_registry(project_ctx)
        tools = ToolExecutor(registry, project_ctx)
        
        session = ChatSession(
            config=config,
            system_prompt="Test prompt",
            permissions=set(),
            iterations=1
        )
        session.state["verbose"] = False  # Disable verbose mode
        
        agent = Agent(mock_llm, tools, session)
        
        # Execute chat
        agent.chat("Test input")
        
        # Verify LLM was called with verbose=False
        mock_llm.chat.assert_called_once()
        call_kwargs = mock_llm.chat.call_args[1]
        assert call_kwargs.get("verbose") is False

    def test_verbose_toggle_during_conversation(self):
        """Test toggling verbose mode mid-conversation."""
        mock_llm = Mock()
        mock_response = Mock()
        mock_message = Mock()
        mock_message.content = "Response"
        mock_message.tool_calls = None
        mock_response.choices = [Mock(message=mock_message)]
        mock_llm.chat.return_value = mock_response
        
        config = Config(
            base_url="http://localhost:11434/v1",
            api_key="test",
            model="qwen3-coder:latest",
            num_ctx=8192,
            editor="vim",
            verbose=False
        )
        
        project_ctx = ProjectContext(".")
        registry = create_default_registry(project_ctx)
        tools = ToolExecutor(registry, project_ctx)
        
        session = ChatSession(
            config=config,
            system_prompt="Test prompt",
            permissions=set(),
            iterations=1
        )
        
        agent = Agent(mock_llm, tools, session)
        
        # First call with verbose=False
        session.state["verbose"] = False
        agent.chat("First message")
        assert mock_llm.chat.call_args[1].get("verbose") is False
        
        # Toggle to verbose=True
        session.state["verbose"] = True
        agent.chat("Second message")
        assert mock_llm.chat.call_args[1].get("verbose") is True
