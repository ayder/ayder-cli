"""Tests for system commands."""

import pytest
from unittest.mock import Mock, patch
from ayder_cli.commands.system import (
    HelpCommand, CompactCommand, VerboseCommand, PlanCommand, ModelCommand, AskCommand
)
from ayder_cli.core.context import SessionContext, ProjectContext
from ayder_cli.core.config import Config
from ayder_cli.prompts import SYSTEM_PROMPT

def _create_session(messages=None, state=None, llm=None):
    return SessionContext(
        config=Config(),
        project=ProjectContext("."),
        messages=messages or [],
        state=state or {},
        llm=llm or Mock(),
        system_prompt=SYSTEM_PROMPT
    )

class TestHelpCommand:
    """Test /help command."""

    @patch("ayder_cli.commands.system.draw_box")
    @patch("ayder_cli.commands.system.get_registry")
    def test_help_command(self, mock_get_registry, mock_draw_box):
        """Test help command output."""
        mock_registry = Mock()
        mock_cmd = Mock()
        mock_cmd.name = "/test"
        mock_cmd.description = "Test command"
        mock_registry.list_commands.return_value = [mock_cmd]
        mock_get_registry.return_value = mock_registry
        
        cmd = HelpCommand()
        session = _create_session()
        result = cmd.execute("", session)
        
        assert result is True
        mock_draw_box.assert_called_once()
        content = mock_draw_box.call_args[0][0]
        assert "Available Commands" in content
        assert "/test" in content
        assert "Test command" in content


class TestCompactCommand:
    """Test /compact command."""

    @patch("ayder_cli.commands.system.draw_box")
    def test_compact_with_conversation(self, mock_draw_box):
        """Test compact command clears and adds prompt."""
        from ayder_cli.commands.system import CompactCommand
        cmd = CompactCommand()
        session = _create_session(
            messages=[
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "hi there"}
            ]
        )
        
        result = cmd.execute("", session)
        
        assert result is True
        # Should have system + compact prompt
        assert len(session.messages) == 2
        assert session.messages[0]["content"] == "sys"
        assert session.messages[1]["role"] == "user"
        assert "compact" in session.messages[1]["content"].lower()
        assert "summarize" in session.messages[1]["content"].lower()
        mock_draw_box.assert_called_once()

    @patch("ayder_cli.commands.system.draw_box")
    def test_compact_no_conversation(self, mock_draw_box):
        """Test compact with no conversation."""
        from ayder_cli.commands.system import CompactCommand
        cmd = CompactCommand()
        session = _create_session(messages=[{"role": "system", "content": "sys"}])
        
        result = cmd.execute("", session)
        
        assert result is True
        assert len(session.messages) == 1  # unchanged
        mock_draw_box.assert_called_once()



class TestVerboseCommand:
    """Test /verbose command."""

    @patch("ayder_cli.commands.system.draw_box")
    def test_verbose_toggle(self, mock_draw_box):
        """Test verbose toggles state."""
        cmd = VerboseCommand()
        session = _create_session(state={"verbose": False})

        # Turn ON
        cmd.execute("", session)
        assert session.state["verbose"] is True
        assert "ON" in mock_draw_box.call_args[0][0]

        # Turn OFF
        cmd.execute("", session)
        assert session.state["verbose"] is False
        assert "OFF" in mock_draw_box.call_args[0][0]


class TestModelCommand:
    """Test /model command."""

    @patch("ayder_cli.commands.system.draw_box")
    def test_model_list(self, mock_draw_box):
        """Test listing models."""
        mock_llm = Mock()
        mock_llm.list_models.return_value = ["model1", "model2"]
        session = _create_session(llm=mock_llm)
        
        cmd = ModelCommand()
        result = cmd.execute("", session)
        
        assert result is True
        mock_llm.list_models.assert_called_once()
        mock_draw_box.assert_called_once()
        # The first call is "Available Models", second might be "Current Model" if list is empty
        # In our case list is NOT empty.
        content = mock_draw_box.call_args[0][0]
        assert "model1" in content
        assert "model2" in content

    @patch("ayder_cli.commands.system.draw_box")
    def test_model_switch(self, mock_draw_box):
        """Test switching models."""
        session = _create_session()
        cmd = ModelCommand()
        
        result = cmd.execute("new-model", session)
        
        assert result is True
        assert session.state["model"] == "new-model"
        mock_draw_box.assert_called_once()
        assert "Switched to model: new-model" in mock_draw_box.call_args[0][0]


class TestAskCommand:
    """Test /ask command."""

    @patch("ayder_cli.commands.system.draw_box")
    def test_ask_no_args(self, mock_draw_box):
        """Test /ask with no question shows usage error."""
        cmd = AskCommand()
        session = _create_session(messages=[])

        result = cmd.execute("", session)

        assert result is True
        # No message should be injected
        assert len(session.messages) == 0
        # no_tools flag should NOT be set
        assert "no_tools" not in session.state
        # Should show usage error
        mock_draw_box.assert_called_once()
        assert "Usage" in mock_draw_box.call_args[0][0]

    @patch("ayder_cli.commands.system.draw_box")
    def test_ask_with_question(self, mock_draw_box):
        """Test /ask sets no_tools flag and injects user message."""
        cmd = AskCommand()
        session = _create_session(messages=[])

        result = cmd.execute("What is REST?", session)

        assert result is True
        # no_tools flag should be set
        assert session.state["no_tools"] is True
        # User message should be injected
        assert len(session.messages) == 1
        assert session.messages[0]["role"] == "user"
        assert session.messages[0]["content"] == "What is REST?"
        mock_draw_box.assert_called_once()

    @patch("ayder_cli.commands.system.draw_box")
    def test_ask_preserves_question(self, mock_draw_box):
        """Test full question text is preserved in injected message."""
        cmd = AskCommand()
        session = _create_session(messages=[])

        long_question = "What is the difference between REST and GraphQL APIs?"
        result = cmd.execute(f"  {long_question}  ", session)

        assert result is True
        assert session.messages[0]["content"] == long_question

