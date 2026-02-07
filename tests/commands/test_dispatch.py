"""Tests for handle_command dispatch."""

import pytest
from unittest.mock import Mock, patch
from ayder_cli.commands import handle_command
from ayder_cli.commands.registry import get_registry
from ayder_cli.commands.base import BaseCommand
from ayder_cli.core.context import SessionContext, ProjectContext
from ayder_cli.core.config import Config

class TestHandleCommand:
    """Test handle_command function."""

    def setup_method(self):
        """Setup registry with mock command."""
        self.registry = get_registry()
        self.mock_cmd = Mock(spec=BaseCommand)
        self.mock_cmd.name = "/test"
        self.mock_cmd.execute.return_value = True
        self.registry.register(self.mock_cmd)

    def _create_session(self):
        return SessionContext(
            config=Config(),
            project=ProjectContext("."),
            messages=[],
            state={}
        )

    @patch("ayder_cli.commands.draw_box")
    def test_unknown_command(self, mock_draw_box):
        """Test unknown command shows error."""
        session = self._create_session()
        result = handle_command("/unknown", session)
        
        assert result is True
        mock_draw_box.assert_called_once()
        assert "Unknown command" in mock_draw_box.call_args[0][0]

    def test_command_dispatch(self):
        """Test command is dispatched to correct handler."""
        session = self._create_session()
        result = handle_command("/test arg1 arg2", session)
            
        assert result is True
        self.mock_cmd.execute.assert_called_once()
        args, passed_session = self.mock_cmd.execute.call_args[0]
        assert args == "arg1 arg2"
        assert passed_session is session
