"""Tests for task commands."""

import pytest
from unittest.mock import Mock, patch
import subprocess
from ayder_cli.commands.tasks import TaskEditCommand, TasksCommand
from ayder_cli.core.config import Config
from ayder_cli.core.context import ProjectContext, SessionContext

def _create_session(config=None, project_root="."):
    return SessionContext(
        config=config or Config(),
        project=ProjectContext(project_root),
        messages=[],
        state={}
    )

class TestTasksCommand:
    """Test /tasks command."""

    @patch("ayder_cli.commands.tasks.list_tasks")
    @patch("ayder_cli.commands.tasks.draw_box")
    def test_tasks_command(self, mock_draw_box, mock_list_tasks):
        """Test tasks command calls list_tasks."""
        mock_list_tasks.return_value = "Task list"
        cmd = TasksCommand()
        session = _create_session()
        
        result = cmd.execute("", session)
        
        assert result is True
        mock_list_tasks.assert_called_once()
        mock_draw_box.assert_called_once()
        assert "Task list" in mock_draw_box.call_args[0][0]

class TestTaskEditCommand:
    """Test /task-edit command."""

    @patch("ayder_cli.commands.tasks.draw_box")
    @patch("ayder_cli.commands.tasks.subprocess.run")
    @patch("ayder_cli.commands.tasks.Path.exists")
    def test_task_edit_with_valid_task_id(
        self, mock_exists, mock_subprocess, mock_draw_box
    ):
        """Test with valid task ID."""
        mock_exists.return_value = True
        mock_subprocess.return_value = Mock()
        
        cmd = TaskEditCommand()
        session = _create_session(config=Config(editor="vim"))
        
        result = cmd.execute("1", session)
        
        assert result is True
        mock_subprocess.assert_called_once()
        call_args = mock_subprocess.call_args[0][0]
        assert call_args[0] == "vim"
        assert "TASK-001.md" in str(call_args[1])

    @patch("ayder_cli.commands.tasks.draw_box")
    def test_task_edit_without_args(self, mock_draw_box):
        """Test without arguments."""
        cmd = TaskEditCommand()
        session = _create_session()
        result = cmd.execute("", session)
        
        assert result is True
        mock_draw_box.assert_called_once()
        assert "Usage:" in mock_draw_box.call_args[0][0]

    @patch("ayder_cli.commands.tasks.draw_box")
    def test_task_edit_invalid_arg(self, mock_draw_box):
        """Test with non-numeric argument."""
        cmd = TaskEditCommand()
        session = _create_session()
        result = cmd.execute("abc", session)
        
        assert result is True
        mock_draw_box.assert_called_once()
        assert "Invalid task ID" in mock_draw_box.call_args[0][0]
