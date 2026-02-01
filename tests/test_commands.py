"""Tests for commands.py module."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import sys
import subprocess

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ayder_cli.commands import handle_command
from ayder_cli.config import Config


class TestHelpCommand:
    """Tests for /help command."""

    @patch("ayder_cli.commands.print")
    @patch("ayder_cli.commands.draw_box")
    def test_help_command_displays_correctly(self, mock_draw_box, mock_print):
        """Test help text is displayed correctly."""
        mock_draw_box.return_value = "help output"
        messages = []
        
        result = handle_command("/help", messages, "system prompt")
        
        assert result is True
        mock_draw_box.assert_called_once()
        # Verify the help text contains expected commands
        help_text = mock_draw_box.call_args[0][0]
        assert "/tools" in help_text
        assert "/tasks" in help_text
        assert "/task-edit" in help_text
        assert "/edit" in help_text
        assert "/verbose" in help_text
        assert "/clear" in help_text
        assert "/undo" in help_text
        assert "exit" in help_text
        assert mock_draw_box.call_args[1]["title"] == "Help"
        assert mock_draw_box.call_args[1]["color_code"] == "33"


class TestToolsCommand:
    """Tests for /tools command."""

    @patch("ayder_cli.commands.print")
    @patch("ayder_cli.commands.draw_box")
    def test_tools_listing_output_format(self, mock_draw_box, mock_print):
        """Test tools listing output format."""
        mock_draw_box.return_value = "tools output"
        messages = []
        
        result = handle_command("/tools", messages, "system prompt")
        
        assert result is True
        mock_draw_box.assert_called_once()
        assert mock_draw_box.call_args[1]["title"] == "Available Tools"
        assert mock_draw_box.call_args[1]["color_code"] == "35"


class TestTasksCommand:
    """Tests for /tasks command."""

    @patch("ayder_cli.commands.print")
    @patch("ayder_cli.commands.draw_box")
    @patch("ayder_cli.commands.list_tasks")
    def test_tasks_command_calls_list_tasks(self, mock_list_tasks, mock_draw_box, mock_print):
        """Test calling list_tasks and displaying result."""
        mock_list_tasks.return_value = "task list output"
        mock_draw_box.return_value = "boxed output"
        messages = []
        
        result = handle_command("/tasks", messages, "system prompt")
        
        assert result is True
        mock_list_tasks.assert_called_once()
        mock_draw_box.assert_called_once_with("task list output", title="Tasks", width=80, color_code="35")


class TestTaskEditCommand:
    """Tests for /task-edit command."""

    @patch("ayder_cli.commands.print")
    @patch("ayder_cli.commands.draw_box")
    @patch("ayder_cli.commands.load_config")
    @patch("ayder_cli.commands.subprocess.run")
    @patch("ayder_cli.commands.Path.exists")
    def test_task_edit_with_valid_task_id(
        self, mock_exists, mock_subprocess, mock_load_config, mock_draw_box, mock_print
    ):
        """Test with valid task ID."""
        mock_exists.return_value = True
        mock_load_config.return_value = Config(editor="vim")
        mock_subprocess.return_value = Mock()
        mock_draw_box.return_value = "success output"
        messages = []
        
        result = handle_command("/task-edit 1", messages, "system prompt")
        
        assert result is True
        mock_subprocess.assert_called_once()
        call_args = mock_subprocess.call_args[0][0]
        assert call_args[0] == "vim"
        assert "TASK-001.md" in call_args[1]

    @patch("ayder_cli.commands.print")
    @patch("ayder_cli.commands.draw_box")
    def test_task_edit_with_missing_task_id(self, mock_draw_box, mock_print):
        """Test with missing task ID (error)."""
        mock_draw_box.return_value = "error output"
        messages = []
        
        result = handle_command("/task-edit", messages, "system prompt")
        
        assert result is True
        mock_draw_box.assert_called_once()
        assert "Usage" in mock_draw_box.call_args[0][0]
        assert mock_draw_box.call_args[1]["title"] == "Error"
        assert mock_draw_box.call_args[1]["color_code"] == "31"

    @patch("ayder_cli.commands.print")
    @patch("ayder_cli.commands.draw_box")
    def test_task_edit_with_invalid_task_id(self, mock_draw_box, mock_print):
        """Test with invalid task ID (non-numeric)."""
        mock_draw_box.return_value = "error output"
        messages = []
        
        result = handle_command("/task-edit abc", messages, "system prompt")
        
        assert result is True
        mock_draw_box.assert_called_once()
        error_msg = mock_draw_box.call_args[0][0]
        assert "Invalid task ID" in error_msg
        assert "abc" in error_msg

    @patch("ayder_cli.commands.print")
    @patch("ayder_cli.commands.draw_box")
    @patch("ayder_cli.commands.Path.exists")
    def test_task_edit_with_nonexistent_task_id(self, mock_exists, mock_draw_box, mock_print):
        """Test with non-existent task ID."""
        mock_exists.return_value = False
        mock_draw_box.return_value = "error output"
        messages = []
        
        result = handle_command("/task-edit 999", messages, "system prompt")
        
        assert result is True
        mock_draw_box.assert_called_once()
        error_msg = mock_draw_box.call_args[0][0]
        assert "TASK-999" in error_msg
        assert "not found" in error_msg

    @patch("ayder_cli.commands.print")
    @patch("ayder_cli.commands.draw_box")
    @patch("ayder_cli.commands.load_config")
    @patch("ayder_cli.commands.subprocess.run")
    @patch("ayder_cli.commands.Path.exists")
    def test_task_edit_editor_not_found(
        self, mock_exists, mock_subprocess, mock_load_config, mock_draw_box, mock_print
    ):
        """Test editor not found error (FileNotFoundError)."""
        mock_exists.return_value = True
        mock_load_config.return_value = Config(editor="nonexistent_editor")
        mock_subprocess.side_effect = FileNotFoundError()
        mock_draw_box.return_value = "error output"
        messages = []
        
        result = handle_command("/task-edit 1", messages, "system prompt")
        
        assert result is True
        mock_draw_box.assert_called()
        last_call = mock_draw_box.call_args
        assert "Editor not found" in last_call[0][0]

    @patch("ayder_cli.commands.print")
    @patch("ayder_cli.commands.draw_box")
    @patch("ayder_cli.commands.load_config")
    @patch("ayder_cli.commands.subprocess.run")
    @patch("ayder_cli.commands.Path.exists")
    def test_task_edit_editor_error(
        self, mock_exists, mock_subprocess, mock_load_config, mock_draw_box, mock_print
    ):
        """Test editor error (CalledProcessError)."""
        mock_exists.return_value = True
        mock_load_config.return_value = Config(editor="vim")
        mock_subprocess.side_effect = subprocess.CalledProcessError(1, "vim")
        mock_draw_box.return_value = "error output"
        messages = []
        
        result = handle_command("/task-edit 1", messages, "system prompt")
        
        assert result is True
        mock_draw_box.assert_called_once()
        assert "Error opening editor" in mock_draw_box.call_args[0][0]

    @patch("ayder_cli.commands.print")
    @patch("ayder_cli.commands.draw_box")
    @patch("ayder_cli.commands.load_config")
    @patch("ayder_cli.commands.subprocess.run")
    @patch("ayder_cli.commands.Path.exists")
    def test_task_edit_with_custom_editor(
        self, mock_exists, mock_subprocess, mock_load_config, mock_draw_box, mock_print
    ):
        """Test with custom editor from config."""
        mock_exists.return_value = True
        mock_load_config.return_value = Config(editor="code")
        mock_subprocess.return_value = Mock()
        mock_draw_box.return_value = "success output"
        messages = []
        
        result = handle_command("/task-edit 5", messages, "system prompt")
        
        assert result is True
        call_args = mock_subprocess.call_args[0][0]
        assert call_args[0] == "code"


class TestEditCommand:
    """Tests for /edit command."""

    @patch("ayder_cli.commands.print")
    @patch("ayder_cli.commands.draw_box")
    @patch("ayder_cli.commands.load_config")
    @patch("ayder_cli.commands.subprocess.run")
    @patch("ayder_cli.commands.Path.exists")
    def test_edit_with_valid_file_path(
        self, mock_exists, mock_subprocess, mock_load_config, mock_draw_box, mock_print
    ):
        """Test with valid file path."""
        mock_exists.return_value = True
        mock_load_config.return_value = Config(editor="vim")
        mock_subprocess.return_value = Mock()
        mock_draw_box.return_value = "success output"
        messages = []
        
        result = handle_command("/edit src/main.py", messages, "system prompt")
        
        assert result is True
        mock_subprocess.assert_called_once()
        call_args = mock_subprocess.call_args[0][0]
        assert call_args[0] == "vim"
        assert call_args[1] == "src/main.py"

    @patch("ayder_cli.commands.print")
    @patch("ayder_cli.commands.draw_box")
    def test_edit_with_missing_file_path(self, mock_draw_box, mock_print):
        """Test with missing file path (error)."""
        mock_draw_box.return_value = "error output"
        messages = []
        
        result = handle_command("/edit", messages, "system prompt")
        
        assert result is True
        mock_draw_box.assert_called_once()
        assert "Usage" in mock_draw_box.call_args[0][0]

    @patch("ayder_cli.commands.print")
    @patch("ayder_cli.commands.draw_box")
    @patch("ayder_cli.commands.Path.exists")
    def test_edit_with_nonexistent_file(self, mock_exists, mock_draw_box, mock_print):
        """Test with non-existent file."""
        mock_exists.return_value = False
        mock_draw_box.return_value = "error output"
        messages = []
        
        result = handle_command("/edit nonexistent.py", messages, "system prompt")
        
        assert result is True
        mock_draw_box.assert_called_once()
        assert "File not found" in mock_draw_box.call_args[0][0]

    @patch("ayder_cli.commands.print")
    @patch("ayder_cli.commands.draw_box")
    @patch("ayder_cli.commands.load_config")
    @patch("ayder_cli.commands.subprocess.run")
    @patch("ayder_cli.commands.Path.exists")
    def test_edit_editor_not_found(
        self, mock_exists, mock_subprocess, mock_load_config, mock_draw_box, mock_print
    ):
        """Test editor not found error."""
        mock_exists.return_value = True
        mock_load_config.return_value = Config(editor="nonexistent")
        mock_subprocess.side_effect = FileNotFoundError()
        mock_draw_box.return_value = "error output"
        messages = []
        
        result = handle_command("/edit file.py", messages, "system prompt")
        
        assert result is True
        last_call = mock_draw_box.call_args
        assert "Editor not found" in last_call[0][0]

    @patch("ayder_cli.commands.print")
    @patch("ayder_cli.commands.draw_box")
    @patch("ayder_cli.commands.load_config")
    @patch("ayder_cli.commands.subprocess.run")
    @patch("ayder_cli.commands.Path.exists")
    def test_edit_editor_error(
        self, mock_exists, mock_subprocess, mock_load_config, mock_draw_box, mock_print
    ):
        """Test editor error (CalledProcessError) for /edit command."""
        mock_exists.return_value = True
        mock_load_config.return_value = Config(editor="vim")
        mock_subprocess.side_effect = subprocess.CalledProcessError(1, "vim")
        mock_draw_box.return_value = "error output"
        messages = []
        
        result = handle_command("/edit file.py", messages, "system prompt")
        
        assert result is True
        mock_draw_box.assert_called_once()
        assert "Error opening editor" in mock_draw_box.call_args[0][0]


class TestVerboseCommand:
    """Tests for /verbose command."""

    @patch("ayder_cli.commands.print")
    @patch("ayder_cli.commands.draw_box")
    def test_verbose_toggle_on(self, mock_draw_box, mock_print):
        """Test toggling verbose ON."""
        mock_draw_box.return_value = "output"
        messages = []
        state = {"verbose": False}
        
        result = handle_command("/verbose", messages, "system prompt", state)
        
        assert result is True
        assert state["verbose"] is True
        mock_draw_box.assert_called_once()
        assert "ON" in mock_draw_box.call_args[0][0]

    @patch("ayder_cli.commands.print")
    @patch("ayder_cli.commands.draw_box")
    def test_verbose_toggle_off(self, mock_draw_box, mock_print):
        """Test toggling verbose OFF."""
        mock_draw_box.return_value = "output"
        messages = []
        state = {"verbose": True}
        
        result = handle_command("/verbose", messages, "system prompt", state)
        
        assert result is True
        assert state["verbose"] is False
        mock_draw_box.assert_called_once()
        assert "OFF" in mock_draw_box.call_args[0][0]

    @patch("ayder_cli.commands.print")
    @patch("ayder_cli.commands.draw_box")
    def test_verbose_with_none_state(self, mock_draw_box, mock_print):
        """Test with None state (error case)."""
        mock_draw_box.return_value = "error output"
        messages = []
        
        result = handle_command("/verbose", messages, "system prompt", None)
        
        assert result is True
        mock_draw_box.assert_called_once()
        assert "not available" in mock_draw_box.call_args[0][0]


class TestClearCommand:
    """Tests for /clear command."""

    @patch("ayder_cli.commands.print")
    @patch("ayder_cli.commands.draw_box")
    def test_clear_clears_messages_list(self, mock_draw_box, mock_print):
        """Test clearing messages list."""
        mock_draw_box.return_value = "output"
        messages = [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "user message"},
            {"role": "assistant", "content": "assistant response"},
        ]
        
        result = handle_command("/clear", messages, "system prompt")
        
        assert result is True
        # After clearing, only system message should remain
        assert len(messages) == 1
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "system prompt"

    @patch("ayder_cli.commands.print")
    @patch("ayder_cli.commands.draw_box")
    def test_clear_preserves_system_prompt(self, mock_draw_box, mock_print):
        """Test system prompt is preserved."""
        mock_draw_box.return_value = "output"
        system_prompt = "custom system prompt"
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "user message"},
        ]
        
        result = handle_command("/clear", messages, system_prompt)
        
        assert result is True
        assert len(messages) == 1
        assert messages[0]["content"] == system_prompt


class TestUndoCommand:
    """Tests for /undo command."""

    @patch("ayder_cli.commands.print")
    @patch("ayder_cli.commands.draw_box")
    def test_undo_removes_last_user_message(self, mock_draw_box, mock_print):
        """Test undo last user message."""
        mock_draw_box.return_value = "output"
        messages = [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "user1"},
            {"role": "assistant", "content": "assistant1"},
            {"role": "user", "content": "user2"},
            {"role": "assistant", "content": "assistant2"},
        ]
        
        result = handle_command("/undo", messages, "system prompt")
        
        assert result is True
        # Should remove user2 and assistant2
        assert len(messages) == 3
        assert messages[-1]["role"] == "assistant"
        assert messages[-1]["content"] == "assistant1"

    @patch("ayder_cli.commands.print")
    @patch("ayder_cli.commands.draw_box")
    def test_undo_with_no_messages(self, mock_draw_box, mock_print):
        """Test undo with no messages (nothing to undo)."""
        mock_draw_box.return_value = "output"
        # Only system message
        messages = [
            {"role": "system", "content": "system"},
        ]
        
        result = handle_command("/undo", messages, "system prompt")
        
        assert result is True
        # Should show "Nothing to undo"
        mock_draw_box.assert_called_once()
        assert "Nothing to undo" in mock_draw_box.call_args[0][0]

    @patch("ayder_cli.commands.print")
    @patch("ayder_cli.commands.draw_box")
    def test_undo_preserves_system_prompt(self, mock_draw_box, mock_print):
        """Test system prompt is never deleted."""
        mock_draw_box.return_value = "output"
        messages = [
            {"role": "system", "content": "system"},
        ]
        
        result = handle_command("/undo", messages, "system prompt")
        
        assert result is True
        # System message should still be there
        assert len(messages) == 1
        assert messages[0]["role"] == "system"

    @patch("ayder_cli.commands.print")
    @patch("ayder_cli.commands.draw_box")
    def test_undo_with_only_user_message(self, mock_draw_box, mock_print):
        """Test undo when only user message exists (no assistant response)."""
        mock_draw_box.return_value = "output"
        messages = [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "user1"},
        ]
        
        result = handle_command("/undo", messages, "system prompt")
        
        assert result is True
        # Should remove the user message
        assert len(messages) == 1
        assert messages[0]["role"] == "system"


class TestUnknownCommand:
    """Tests for unknown command handling."""

    @patch("ayder_cli.commands.print")
    @patch("ayder_cli.commands.draw_box")
    def test_unknown_command_error_message(self, mock_draw_box, mock_print):
        """Test error message for unknown command."""
        mock_draw_box.return_value = "error output"
        messages = []
        
        result = handle_command("/unknown", messages, "system prompt")
        
        assert result is True
        mock_draw_box.assert_called_once()
        error_msg = mock_draw_box.call_args[0][0]
        assert "Unknown command" in error_msg
        assert "/unknown" in error_msg
        assert mock_draw_box.call_args[1]["title"] == "Error"
        assert mock_draw_box.call_args[1]["color_code"] == "31"


class TestCommandCaseHandling:
    """Tests for command case handling."""

    @patch("ayder_cli.commands.print")
    @patch("ayder_cli.commands.draw_box")
    def test_command_case_insensitive(self, mock_draw_box, mock_print):
        """Test commands are case-insensitive."""
        mock_draw_box.return_value = "output"
        messages = []
        
        # Test uppercase command
        result = handle_command("/HELP", messages, "system prompt")
        assert result is True
        
        # Test mixed case
        result = handle_command("/Help", messages, "system prompt")
        assert result is True
        
        # Test lowercase
        result = handle_command("/help", messages, "system prompt")
        assert result is True

    @patch("ayder_cli.commands.print")
    @patch("ayder_cli.commands.draw_box")
    def test_args_preserved_case_sensitive(self, mock_draw_box, mock_print):
        """Test that arguments preserve case sensitivity."""
        mock_draw_box.return_value = "output"
        messages = []
        
        # The file path should be preserved as-is
        result = handle_command("/edit MyFile.PY", messages, "system prompt")
        assert result is True
