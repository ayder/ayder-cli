"""Tests for commands/tools.py — ToolsCommand."""
import pytest
from unittest.mock import Mock, patch
from ayder_cli.commands.tools import ToolsCommand
from ayder_cli.core.context import SessionContext


@pytest.fixture
def tools_command():
    return ToolsCommand()


@pytest.fixture
def mock_session():
    """Create a mock SessionContext."""
    session = Mock(spec=SessionContext)
    return session


class TestToolsCommand:
    """Tests for ToolsCommand."""

    def test_name_property(self, tools_command):
        assert tools_command.name == "/tools"

    def test_description_property(self, tools_command):
        assert "tool" in tools_command.description.lower()

    @patch("ayder_cli.commands.tools.draw_box")
    def test_execute_lists_tools(self, mock_draw_box, tools_command, mock_session):
        """execute() formats tool names and descriptions, passes to draw_box."""
        result = tools_command.execute("", mock_session)
        assert result is True
        mock_draw_box.assert_called_once()
        call_args = mock_draw_box.call_args
        output_text = call_args[0][0]  # first positional arg
        # Verify some known tools appear
        assert "read_file" in output_text
        assert "write_file" in output_text
        assert "run_shell_command" in output_text

    @patch("ayder_cli.commands.tools.draw_box")
    def test_execute_uses_correct_title_and_color(self, mock_draw_box, tools_command, mock_session):
        """Verify draw_box is called with title='Available Tools' and color_code='35'."""
        tools_command.execute("", mock_session)
        call_kwargs = mock_draw_box.call_args[1]
        assert call_kwargs.get("title") == "Available Tools"
        assert call_kwargs.get("color_code") == "35"

    @patch("ayder_cli.commands.tools.draw_box")
    def test_execute_includes_tool_descriptions(self, mock_draw_box, tools_command, mock_session):
        """Verify that tool descriptions are included in the output."""
        tools_command.execute("", mock_session)
        call_args = mock_draw_box.call_args
        output_text = call_args[0][0]
        # Check for some known tool descriptions
        assert "description" in output_text.lower() or "read" in output_text.lower()
