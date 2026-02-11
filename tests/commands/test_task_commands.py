"""Tests for task commands."""

import pytest
from unittest.mock import Mock, patch, MagicMock
import subprocess
from pathlib import Path
import tempfile

from ayder_cli.commands.tasks import (
    TasksCommand, TaskEditCommand, TaskRunCommand, ImplementAllCommand,
    ArchiveCompletedTasksCommand,
)
from ayder_cli.core.config import Config
from ayder_cli.core.context import ProjectContext, SessionContext
from ayder_cli.services.llm import LLMProvider


def _create_session(config=None, project_root="."):
    return SessionContext(
        config=config or Config(),
        project=ProjectContext(project_root),
        messages=[],
        state={},
        llm=Mock(spec=LLMProvider)
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

    def test_tasks_command_name(self):
        """Test command name property."""
        cmd = TasksCommand()
        assert cmd.name == "/tasks"

    def test_tasks_command_description(self):
        """Test command description property."""
        cmd = TasksCommand()
        assert cmd.description == "List all saved tasks"


class TestTaskEditCommand:
    """Test /task-edit command."""

    def test_task_edit_command_name(self):
        """Test command name property."""
        cmd = TaskEditCommand()
        assert cmd.name == "/task-edit"

    def test_task_edit_command_description(self):
        """Test command description property."""
        cmd = TaskEditCommand()
        assert "Edit task" in cmd.description

    @patch("ayder_cli.commands.tasks.draw_box")
    @patch("ayder_cli.commands.tasks.subprocess.run")
    @patch("ayder_cli.commands.tasks._get_task_path_by_id")
    def test_task_edit_with_valid_task_id(
        self, mock_get_path, mock_subprocess, mock_draw_box
    ):
        """Test with valid task ID."""
        mock_get_path.return_value = Path("/tmp/tasks/TASK-001-test-task.md")
        mock_subprocess.return_value = Mock()

        cmd = TaskEditCommand()
        session = _create_session(config=Config(editor="vim"))

        result = cmd.execute("1", session)

        assert result is True
        mock_subprocess.assert_called_once()
        call_args = mock_subprocess.call_args[0][0]
        assert call_args[0] == "vim"
        assert "TASK-001-test-task.md" in str(call_args[1])

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

    @patch("ayder_cli.commands.tasks.draw_box")
    @patch("ayder_cli.commands.tasks._get_task_path_by_id")
    def test_task_edit_task_not_found(self, mock_get_path, mock_draw_box):
        """Test when task ID doesn't exist."""
        mock_get_path.return_value = None

        cmd = TaskEditCommand()
        session = _create_session()

        result = cmd.execute("999", session)

        assert result is True
        mock_draw_box.assert_called_once()
        assert "not found" in mock_draw_box.call_args[0][0]

    @patch("ayder_cli.commands.tasks.draw_box")
    @patch("ayder_cli.commands.tasks.subprocess.run")
    @patch("ayder_cli.commands.tasks._get_task_path_by_id")
    def test_task_edit_editor_called_process_error(
        self, mock_get_path, mock_subprocess, mock_draw_box
    ):
        """Test editor returns non-zero exit code."""
        mock_get_path.return_value = Path("/tmp/tasks/TASK-001-test-task.md")
        mock_subprocess.side_effect = subprocess.CalledProcessError(1, "vim")

        cmd = TaskEditCommand()
        session = _create_session(config=Config(editor="vim"))

        result = cmd.execute("1", session)

        assert result is True
        mock_draw_box.assert_called_once()
        assert "Error opening editor" in mock_draw_box.call_args[0][0]

    @patch("ayder_cli.commands.tasks.draw_box")
    @patch("ayder_cli.commands.tasks.subprocess.run")
    @patch("ayder_cli.commands.tasks._get_task_path_by_id")
    def test_task_edit_editor_not_found(
        self, mock_get_path, mock_subprocess, mock_draw_box
    ):
        """Test when editor executable is not found."""
        mock_get_path.return_value = Path("/tmp/tasks/TASK-001-test-task.md")
        mock_subprocess.side_effect = FileNotFoundError("vim not found")

        cmd = TaskEditCommand()
        session = _create_session(config=Config(editor="vim"))

        result = cmd.execute("1", session)

        assert result is True
        mock_draw_box.assert_called_once()
        assert "Editor not found" in mock_draw_box.call_args[0][0]


class TestTaskRunCommand:
    """Test /implement command."""

    def test_task_run_command_name(self):
        """Test command name property."""
        cmd = TaskRunCommand()
        assert cmd.name == "/implement"

    def test_task_run_command_description(self):
        """Test command description property."""
        cmd = TaskRunCommand()
        assert "Run a task" in cmd.description

    @patch("ayder_cli.commands.tasks.draw_box")
    @patch("ayder_cli.commands.tasks._get_tasks_dir")
    def test_implement_without_args(self, mock_get_dir, mock_draw_box):
        """Test without arguments shows usage."""
        mock_get_dir.return_value = Mock(exists=lambda: True)
        cmd = TaskRunCommand()
        session = _create_session()
        
        result = cmd.execute("", session)
        
        assert result is True
        mock_draw_box.assert_called_once()
        assert "Usage:" in mock_draw_box.call_args[0][0]

    @patch("ayder_cli.commands.tasks.draw_box")
    @patch("ayder_cli.commands.tasks._get_tasks_dir")
    @patch("ayder_cli.commands.tasks._get_task_path_by_id")
    def test_implement_by_id_success(self, mock_get_path, mock_get_dir, mock_draw_box):
        """Test implementing a task by ID."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tasks_dir = Path(tmpdir) / ".ayder" / "tasks"
            tasks_dir.mkdir(parents=True)
            task_file = tasks_dir / "TASK-001-test-task.md"
            task_file.write_text("# Test Task")
            
            mock_get_dir.return_value = tasks_dir
            mock_get_path.return_value = task_file

            cmd = TaskRunCommand()
            session = _create_session(project_root=tmpdir)
            
            result = cmd.execute("1", session)
            
            assert result is True
            assert len(session.messages) == 1
            assert "analyze file" in session.messages[0]["content"].lower()

    @patch("ayder_cli.commands.tasks.draw_box")
    @patch("ayder_cli.commands.tasks._get_tasks_dir")
    def test_implement_no_matching_tasks(self, mock_get_dir, mock_draw_box):
        """Test when no tasks match the query."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tasks_dir = Path(tmpdir) / ".ayder" / "tasks"
            tasks_dir.mkdir(parents=True)
            
            mock_get_dir.return_value = tasks_dir

            cmd = TaskRunCommand()
            session = _create_session(project_root=tmpdir)
            
            result = cmd.execute("nonexistent", session)
            
            assert result is True
            mock_draw_box.assert_called_once()
            assert "No tasks found" in mock_draw_box.call_args[0][0]

    @patch("ayder_cli.commands.tasks.draw_box")
    @patch("ayder_cli.commands.tasks._get_tasks_dir")
    def test_implement_by_pattern_match(self, mock_get_dir, mock_draw_box):
        """Test implementing tasks matching a pattern."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tasks_dir = Path(tmpdir) / ".ayder" / "tasks"
            tasks_dir.mkdir(parents=True)
            
            # Create task files
            task1 = tasks_dir / "TASK-001-authentication.md"
            task1.write_text("# Implement Authentication")
            task2 = tasks_dir / "TASK-002-authorization.md"
            task2.write_text("# Implement Authorization")
            
            mock_get_dir.return_value = tasks_dir

            cmd = TaskRunCommand()
            session = _create_session(project_root=tmpdir)
            
            result = cmd.execute("auth", session)
            
            assert result is True
            # Should find both auth tasks
            assert len(session.messages) == 2

    @patch("ayder_cli.commands.tasks.draw_box")
    @patch("ayder_cli.commands.tasks._get_tasks_dir")
    def test_implement_multiple_matches_shows_list(self, mock_get_dir, mock_draw_box):
        """Test that multiple matches shows task list before running."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tasks_dir = Path(tmpdir) / ".ayder" / "tasks"
            tasks_dir.mkdir(parents=True)
            
            # Create multiple task files
            task1 = tasks_dir / "TASK-001-test-alpha.md"
            task1.write_text("# Test Alpha")
            task2 = tasks_dir / "TASK-002-test-beta.md"
            task2.write_text("# Test Beta")
            
            mock_get_dir.return_value = tasks_dir

            cmd = TaskRunCommand()
            session = _create_session(project_root=tmpdir)
            
            result = cmd.execute("test", session)
            
            assert result is True
            # Should show the list of matching tasks in first call
            # First call is the summary, subsequent calls are for each task
            all_calls = [call[0][0] for call in mock_draw_box.call_args_list]
            assert any("Found 2 matching tasks" in text for text in all_calls)


class TestImplementAllCommand:
    """Test /implement-all command."""

    def test_implement_all_command_name(self):
        """Test command name property."""
        cmd = ImplementAllCommand()
        assert cmd.name == "/implement-all"

    def test_implement_all_command_description(self):
        """Test command description property."""
        cmd = ImplementAllCommand()
        assert "Implement all undone tasks" in cmd.description

    @patch("ayder_cli.commands.tasks.draw_box")
    @patch("ayder_cli.commands.tasks._get_tasks_dir")
    def test_implement_all_no_tasks_dir(self, mock_get_dir, mock_draw_box):
        """Test when tasks directory doesn't exist."""
        mock_dir = Mock(exists=lambda: False)
        mock_get_dir.return_value = mock_dir
        
        cmd = ImplementAllCommand()
        session = _create_session()
        
        result = cmd.execute("", session)
        
        assert result is True
        mock_draw_box.assert_called_once()
        assert "No tasks directory" in mock_draw_box.call_args[0][0]

    @patch("ayder_cli.commands.tasks.draw_box")
    @patch("ayder_cli.commands.tasks._get_tasks_dir")
    def test_implement_all_no_pending_tasks(self, mock_get_dir, mock_draw_box):
        """Test when no pending tasks exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tasks_dir = Path(tmpdir) / ".ayder" / "tasks"
            tasks_dir.mkdir(parents=True)
            mock_get_dir.return_value = tasks_dir
            
            cmd = ImplementAllCommand()
            session = _create_session()
            
            result = cmd.execute("", session)
            
            assert result is True
            mock_draw_box.assert_called_once()
            assert "No pending tasks" in mock_draw_box.call_args[0][0]

    @patch("ayder_cli.commands.tasks.draw_box")
    @patch("ayder_cli.commands.tasks._get_tasks_dir")
    def test_implement_all_with_pending_tasks(self, mock_get_dir, mock_draw_box):
        """Test with pending tasks adds message."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tasks_dir = Path(tmpdir) / ".ayder" / "tasks"
            tasks_dir.mkdir(parents=True)
            
            # Create a pending task
            task_file = tasks_dir / "TASK-001-test-task.md"
            task_file.write_text("# Test Task\n\n- **Status:** pending\n")
            
            mock_get_dir.return_value = tasks_dir
            
            cmd = ImplementAllCommand()
            session = _create_session()
            
            result = cmd.execute("", session)
            
            assert result is True
            # Should add a message for the agent
            assert len(session.messages) == 1
            assert "implement each undone task" in session.messages[0]["content"].lower()

    @patch("ayder_cli.commands.tasks.draw_box")
    @patch("ayder_cli.commands.tasks._get_tasks_dir")
    def test_implement_all_with_todo_status(self, mock_get_dir, mock_draw_box):
        """Test with 'todo' status (alternative to pending)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tasks_dir = Path(tmpdir) / ".ayder" / "tasks"
            tasks_dir.mkdir(parents=True)
            
            # Create a todo task
            task_file = tasks_dir / "TASK-001-test-task.md"
            task_file.write_text("# Test Task\n\n- **Status:** todo\n")
            
            mock_get_dir.return_value = tasks_dir
            
            cmd = ImplementAllCommand()
            session = _create_session()
            
            result = cmd.execute("", session)
            
            assert result is True
            assert len(session.messages) == 1

    @patch("ayder_cli.commands.tasks.draw_box")
    @patch("ayder_cli.commands.tasks._get_tasks_dir")
    def test_implement_all_skips_completed_tasks(self, mock_get_dir, mock_draw_box):
        """Test that completed tasks are skipped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tasks_dir = Path(tmpdir) / ".ayder" / "tasks"
            tasks_dir.mkdir(parents=True)
            
            # Create a completed task
            task_file = tasks_dir / "TASK-001-test-task.md"
            task_file.write_text("# Test Task\n\n- **Status:** done\n")
            
            mock_get_dir.return_value = tasks_dir
            
            cmd = ImplementAllCommand()
            session = _create_session()
            
            result = cmd.execute("", session)
            
            assert result is True
            mock_draw_box.assert_called_once()
            assert "No pending tasks" in mock_draw_box.call_args[0][0]

    @patch("ayder_cli.commands.tasks.draw_box")
    @patch("ayder_cli.commands.tasks._get_tasks_dir")
    def test_implement_all_skips_invalid_task_files(self, mock_get_dir, mock_draw_box):
        """Test that files without valid task IDs are skipped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tasks_dir = Path(tmpdir) / ".ayder" / "tasks"
            tasks_dir.mkdir(parents=True)
            
            # Create invalid task file (no ID)
            task_file = tasks_dir / "invalid-task.md"
            task_file.write_text("# Invalid Task\n\n- **Status:** pending\n")
            
            mock_get_dir.return_value = tasks_dir
            
            cmd = ImplementAllCommand()
            session = _create_session()
            
            result = cmd.execute("", session)
            
            assert result is True
            # Should report no pending tasks since invalid file is skipped
            assert "No pending tasks" in mock_draw_box.call_args[0][0]

    @patch("ayder_cli.commands.tasks.draw_box")
    @patch("ayder_cli.commands.tasks._get_tasks_dir")
    def test_implement_all_multiple_pending_tasks(self, mock_get_dir, mock_draw_box):
        """Test with multiple pending tasks."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tasks_dir = Path(tmpdir) / ".ayder" / "tasks"
            tasks_dir.mkdir(parents=True)
            
            # Create multiple pending tasks
            task1 = tasks_dir / "TASK-002-second-task.md"
            task1.write_text("# Second Task\n\n- **Status:** pending\n")
            task2 = tasks_dir / "TASK-001-first-task.md"
            task2.write_text("# First Task\n\n- **Status:** pending\n")
            
            mock_get_dir.return_value = tasks_dir
            
            cmd = ImplementAllCommand()
            session = _create_session()
            
            result = cmd.execute("", session)
            
            assert result is True
            # Should show 2 pending tasks
            call_text = mock_draw_box.call_args[0][0]
            assert "Found 2 pending tasks" in call_text
            assert len(session.messages) == 1


class TestArchiveCompletedTasksCommand:
    """Test /archive-completed-tasks command."""

    def test_command_name(self):
        cmd = ArchiveCompletedTasksCommand()
        assert cmd.name == "/archive-completed-tasks"

    def test_command_description(self):
        cmd = ArchiveCompletedTasksCommand()
        assert "completed" in cmd.description.lower() or "done" in cmd.description.lower()

    @patch("ayder_cli.commands.tasks.draw_box")
    @patch("ayder_cli.commands.tasks._get_tasks_dir")
    def test_no_tasks_dir(self, mock_get_dir, mock_draw_box):
        """Test when tasks directory doesn't exist."""
        mock_dir = Mock(exists=lambda: False)
        mock_get_dir.return_value = mock_dir

        cmd = ArchiveCompletedTasksCommand()
        session = _create_session()

        result = cmd.execute("", session)

        assert result is True
        mock_draw_box.assert_called_once()
        assert "No tasks directory" in mock_draw_box.call_args[0][0]

    @patch("ayder_cli.commands.tasks.draw_box")
    @patch("ayder_cli.commands.tasks._get_tasks_dir")
    def test_no_completed_tasks(self, mock_get_dir, mock_draw_box):
        """Test when no tasks have done status."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tasks_dir = Path(tmpdir) / ".ayder" / "tasks"
            tasks_dir.mkdir(parents=True)
            task = tasks_dir / "TASK-001-test.md"
            task.write_text("# Test\n\n- **Status:** pending\n")

            mock_get_dir.return_value = tasks_dir

            cmd = ArchiveCompletedTasksCommand()
            session = _create_session()

            result = cmd.execute("", session)

            assert result is True
            assert "No completed tasks" in mock_draw_box.call_args[0][0]

    @patch("ayder_cli.commands.tasks.draw_box")
    @patch("ayder_cli.commands.tasks._get_tasks_dir")
    def test_archives_done_task(self, mock_get_dir, mock_draw_box):
        """Test that done tasks are moved to task_archive."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tasks_dir = Path(tmpdir) / ".ayder" / "tasks"
            tasks_dir.mkdir(parents=True)
            task = tasks_dir / "TASK-001-done-task.md"
            task.write_text("# Done Task\n\n- **Status:** done\n")

            mock_get_dir.return_value = tasks_dir

            cmd = ArchiveCompletedTasksCommand()
            session = _create_session()

            result = cmd.execute("", session)

            assert result is True
            # Original file should be gone
            assert not task.exists()
            # Archive should contain the file
            archive_dir = Path(tmpdir) / ".ayder" / "task_archive"
            assert (archive_dir / "TASK-001-done-task.md").exists()
            assert "Archived 1" in mock_draw_box.call_args[0][0]

    @patch("ayder_cli.commands.tasks.draw_box")
    @patch("ayder_cli.commands.tasks._get_tasks_dir")
    def test_archives_multiple_done_tasks(self, mock_get_dir, mock_draw_box):
        """Test archiving multiple completed tasks."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tasks_dir = Path(tmpdir) / ".ayder" / "tasks"
            tasks_dir.mkdir(parents=True)
            t1 = tasks_dir / "TASK-001-first.md"
            t1.write_text("# First\n\n- **Status:** done\n")
            t2 = tasks_dir / "TASK-002-second.md"
            t2.write_text("# Second\n\n- **Status:** done\n")
            t3 = tasks_dir / "TASK-003-pending.md"
            t3.write_text("# Pending\n\n- **Status:** pending\n")

            mock_get_dir.return_value = tasks_dir

            cmd = ArchiveCompletedTasksCommand()
            session = _create_session()

            result = cmd.execute("", session)

            assert result is True
            # Only done tasks moved
            assert not t1.exists()
            assert not t2.exists()
            assert t3.exists()  # pending stays
            archive_dir = Path(tmpdir) / ".ayder" / "task_archive"
            assert (archive_dir / "TASK-001-first.md").exists()
            assert (archive_dir / "TASK-002-second.md").exists()
            assert "Archived 2" in mock_draw_box.call_args[0][0]

    @patch("ayder_cli.commands.tasks.draw_box")
    @patch("ayder_cli.commands.tasks._get_tasks_dir")
    def test_creates_archive_directory(self, mock_get_dir, mock_draw_box):
        """Test that archive directory is created if missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tasks_dir = Path(tmpdir) / ".ayder" / "tasks"
            tasks_dir.mkdir(parents=True)
            task = tasks_dir / "TASK-001-test.md"
            task.write_text("# Test\n\n- **Status:** done\n")

            archive_dir = Path(tmpdir) / ".ayder" / "task_archive"
            assert not archive_dir.exists()

            mock_get_dir.return_value = tasks_dir

            cmd = ArchiveCompletedTasksCommand()
            session = _create_session()
            cmd.execute("", session)

            assert archive_dir.exists()

    @patch("ayder_cli.commands.tasks.draw_box")
    @patch("ayder_cli.commands.tasks._get_tasks_dir")
    def test_case_insensitive_status_check(self, mock_get_dir, mock_draw_box):
        """Test that status check is case-insensitive."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tasks_dir = Path(tmpdir) / ".ayder" / "tasks"
            tasks_dir.mkdir(parents=True)
            task = tasks_dir / "TASK-001-test.md"
            task.write_text("# Test\n\n- **Status:** Done\n")

            mock_get_dir.return_value = tasks_dir

            cmd = ArchiveCompletedTasksCommand()
            session = _create_session()
            cmd.execute("", session)

            assert not task.exists()
            archive_dir = Path(tmpdir) / ".ayder" / "task_archive"
            assert (archive_dir / "TASK-001-test.md").exists()

    @patch("ayder_cli.commands.tasks.draw_box")
    @patch("ayder_cli.commands.tasks._get_tasks_dir")
    def test_skips_files_without_task_id(self, mock_get_dir, mock_draw_box):
        """Test that files without valid TASK-NNN prefix are skipped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tasks_dir = Path(tmpdir) / ".ayder" / "tasks"
            tasks_dir.mkdir(parents=True)
            invalid = tasks_dir / "notes.md"
            invalid.write_text("# Notes\n\n- **Status:** done\n")

            mock_get_dir.return_value = tasks_dir

            cmd = ArchiveCompletedTasksCommand()
            session = _create_session()
            cmd.execute("", session)

            # Invalid file should remain
            assert invalid.exists()
            assert "No completed tasks" in mock_draw_box.call_args[0][0]
