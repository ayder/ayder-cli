"""Tests for commands/files.py — EditCommand."""
import subprocess
from pathlib import Path
import pytest
from unittest.mock import Mock, patch
from ayder_cli.commands.files import EditCommand
from ayder_cli.core.context import SessionContext


@pytest.fixture
def edit_command():
    return EditCommand()


@pytest.fixture
def mock_session():
    """Create a mock SessionContext with config.editor."""
    session = Mock(spec=SessionContext)
    session.config = Mock()
    session.config.editor = "vim"
    return session


class TestEditCommand:
    """Tests for EditCommand."""

    def test_name_property(self, edit_command):
        assert edit_command.name == "/edit"

    def test_description_property(self, edit_command):
        assert "editor" in edit_command.description.lower() or "file" in edit_command.description.lower()

    @patch("ayder_cli.commands.files.draw_box")
    def test_no_args_shows_usage(self, mock_draw_box, edit_command, mock_session):
        """No arguments prints usage and returns True."""
        result = edit_command.execute("", mock_session)
        assert result is True
        mock_draw_box.assert_called_once()
        call_args = mock_draw_box.call_args
        assert "Usage" in str(call_args)

    @patch("ayder_cli.commands.files.draw_box")
    @patch("ayder_cli.commands.files.subprocess.run")
    def test_opens_editor_successfully(self, mock_run, mock_draw_box, edit_command, mock_session, tmp_path):
        """Opens editor and prints success on normal exit."""
        test_file = tmp_path / "test.py"
        test_file.write_text("content")
        result = edit_command.execute(str(test_file), mock_session)
        assert result is True
        mock_run.assert_called_once_with(["vim", str(test_file)], check=True)
        # Success draw_box called
        assert any("Success" in str(c) for c in mock_draw_box.call_args_list)

    @patch("ayder_cli.commands.files.draw_box")
    @patch("ayder_cli.commands.files.subprocess.run", side_effect=subprocess.CalledProcessError(1, "vim"))
    def test_editor_process_error(self, mock_run, mock_draw_box, edit_command, mock_session):
        """CalledProcessError prints editor error."""
        result = edit_command.execute("file.py", mock_session)
        assert result is True
        assert any("Error" in str(c) for c in mock_draw_box.call_args_list)

    @patch("ayder_cli.commands.files.draw_box")
    @patch("ayder_cli.commands.files.subprocess.run", side_effect=FileNotFoundError())
    def test_editor_not_found(self, mock_run, mock_draw_box, edit_command, mock_session):
        """FileNotFoundError prints config hint."""
        result = edit_command.execute("file.py", mock_session)
        assert result is True
        assert any("not found" in str(c).lower() or "config" in str(c).lower() for c in mock_draw_box.call_args_list)

    @patch("ayder_cli.commands.files.draw_box")
    @patch("ayder_cli.commands.files.subprocess.run")
    def test_uses_configured_editor(self, mock_run, mock_draw_box, edit_command, mock_session):
        """Uses the editor from session config."""
        mock_session.config.editor = "nano"
        result = edit_command.execute("file.py", mock_session)
        mock_run.assert_called_once_with(["nano", "file.py"], check=True)
