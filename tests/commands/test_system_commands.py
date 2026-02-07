"""Tests for system commands."""

import pytest
from unittest.mock import Mock, patch
from ayder_cli.commands.system import HelpCommand, ClearCommand, VerboseCommand
from ayder_cli.core.context import SessionContext, ProjectContext
from ayder_cli.core.config import Config

def _create_session(messages=None, state=None):
    return SessionContext(
        config=Config(),
        project=ProjectContext("."),
        messages=messages or [],
        state=state or {}
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

class TestClearCommand:
    """Test /clear command."""

    @patch("ayder_cli.commands.system.draw_box")
    def test_clear_command(self, mock_draw_box):
        """Test clear command resets messages."""
        cmd = ClearCommand()
        session = _create_session(
            messages=[
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "hi"}
            ]
        )
        
        result = cmd.execute("", session)
        
        assert result is True
        assert len(session.messages) == 1
        assert session.messages[0]["content"] == "sys"
        mock_draw_box.assert_called_once()

    @patch("ayder_cli.commands.system.draw_box")
    def test_clear_command_empty(self, mock_draw_box):
        """Test clear command with empty messages."""
        cmd = ClearCommand()
        session = _create_session(messages=[])
        
        result = cmd.execute("", session)
        
        assert result is True
        assert len(session.messages) == 0

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
