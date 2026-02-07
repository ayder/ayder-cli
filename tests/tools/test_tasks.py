"""Tests for tasks.py module."""

import re
import pytest
from datetime import datetime
from pathlib import Path

from ayder_cli.tasks import (
    _ensure_tasks_dir,
    _extract_id,
    _next_id,
    create_task,
    _parse_status,
    _parse_title,
    list_tasks,
    show_task,
    _update_task_status,
    implement_task,
    implement_all_tasks,
)
from ayder_cli.core.context import ProjectContext
from ayder_cli.core.result import ToolSuccess, ToolError


@pytest.fixture
def project_context(tmp_path):
    """Create a project context with tmp_path as root."""
    return ProjectContext(str(tmp_path))


class TestEnsureTasksDir:
    """Test _ensure_tasks_dir() function."""

    def test_directory_creation_when_not_exists(self, tmp_path, project_context):
        """Test directory is created when it doesn't exist."""
        mock_tasks_dir = tmp_path / ".ayder" / "tasks"
        
        assert not mock_tasks_dir.exists()
        _ensure_tasks_dir(project_context)
        assert mock_tasks_dir.exists()
        assert mock_tasks_dir.is_dir()

    def test_no_error_when_directory_exists(self, tmp_path, project_context):
        """Test no error when directory already exists."""
        mock_tasks_dir = tmp_path / ".ayder" / "tasks"
        mock_tasks_dir.mkdir(parents=True)
        
        # Should not raise an error
        _ensure_tasks_dir(project_context)
        assert mock_tasks_dir.exists()


class TestExtractId:
    """Test _extract_id() function."""

    def test_extract_id_from_valid_filenames(self):
        """Test extracting ID from valid filenames."""
        assert _extract_id("TASK-001.md") == 1
        assert _extract_id("TASK-123.md") == 123
        assert _extract_id("TASK-999.md") == 999
        assert _extract_id("TASK-000.md") == 0

    def test_return_none_for_invalid_filenames(self):
        """Test returning None for invalid filenames."""
        assert _extract_id("task-001.md") is None  # lowercase
        assert _extract_id("TASK-01.md") == 1      # 2 digits - valid (regex accepts any digits)
        assert _extract_id("TASK-1.md") == 1       # 1 digit - valid (regex accepts any digits)
        assert _extract_id("TASK-1234.md") == 1234 # 4 digits - valid (regex accepts any digits)
        assert _extract_id("task_001.md") is None  # underscore
        assert _extract_id("001.md") is None       # missing prefix
        assert _extract_id("TASK-001.txt") is None # wrong extension
        assert _extract_id("README.md") is None    # no ID
        assert _extract_id("") is None             # empty string


class TestNextId:
    """Test _next_id() function."""

    def test_when_no_tasks_exist(self, tmp_path, project_context):
        """Test returns 1 when no tasks exist."""
        assert _next_id(project_context) == 1

    def test_with_existing_tasks(self, tmp_path, project_context):
        """Test returns max + 1 with existing tasks."""
        mock_tasks_dir = tmp_path / ".ayder" / "tasks"
        mock_tasks_dir.mkdir(parents=True)
        
        # Create some task files
        (mock_tasks_dir / "TASK-001.md").write_text("task 1")
        (mock_tasks_dir / "TASK-003.md").write_text("task 3")
        (mock_tasks_dir / "TASK-005.md").write_text("task 5")
        
        assert _next_id(project_context) == 6

    def test_with_gaps_in_task_ids(self, tmp_path, project_context):
        """Test correctly handles gaps in task IDs."""
        mock_tasks_dir = tmp_path / ".ayder" / "tasks"
        mock_tasks_dir.mkdir(parents=True)
        
        # Create tasks with gaps
        (mock_tasks_dir / "TASK-001.md").write_text("task 1")
        (mock_tasks_dir / "TASK-010.md").write_text("task 10")
        
        assert _next_id(project_context) == 11

    def test_ignores_non_task_files(self, tmp_path, project_context):
        """Test ignores files that don't match TASK-XXX.md pattern."""
        mock_tasks_dir = tmp_path / ".ayder" / "tasks"
        mock_tasks_dir.mkdir(parents=True)
        
        # Create valid and invalid files
        (mock_tasks_dir / "TASK-005.md").write_text("valid task")
        (mock_tasks_dir / "README.md").write_text("readme")
        (mock_tasks_dir / "other.txt").write_text("text file")
        (mock_tasks_dir / ".hidden").write_text("hidden file")
        
        assert _next_id(project_context) == 6


class TestCreateTask:
    """Test create_task() function."""

    def test_create_task_with_title_only(self, tmp_path, project_context):
        """Test creating task with title only."""
        result = create_task(project_context, "Test Task")

        assert isinstance(result, ToolSuccess)
        assert "Task TASK-001 created" in result
        mock_tasks_dir = tmp_path / ".ayder" / "tasks"
        assert (mock_tasks_dir / "TASK-001.md").exists()

    def test_create_task_with_title_and_description(self, tmp_path, project_context):
        """Test creating task with title and description."""
        result = create_task(project_context, "Test Task", "This is a description")
        
        assert "Task TASK-001 created" in result
        mock_tasks_dir = tmp_path / ".ayder" / "tasks"
        content = (mock_tasks_dir / "TASK-001.md").read_text()
        assert "This is a description" in content

    def test_verify_task_file_content_format(self, tmp_path, project_context):
        """Verify task file content format."""
        create_task(project_context, "My Test Task", "Test description")
        
        mock_tasks_dir = tmp_path / ".ayder" / "tasks"
        content = (mock_tasks_dir / "TASK-001.md").read_text()
        
        # Check format
        assert content.startswith("# My Test Task")
        assert "- **ID:** TASK-001" in content
        assert "- **Status:** pending" in content
        assert "- **Created:**" in content
        assert "## Description" in content

    def test_verify_task_id_formatting(self, tmp_path, project_context):
        """Verify task ID formatting (TASK-XXX.md)."""
        # Create multiple tasks
        create_task(project_context, "Task 1")
        create_task(project_context, "Task 2")
        create_task(project_context, "Task 3")
        
        mock_tasks_dir = tmp_path / ".ayder" / "tasks"
        # Verify 3-digit formatting
        assert (mock_tasks_dir / "TASK-001.md").exists()
        assert (mock_tasks_dir / "TASK-002.md").exists()
        assert (mock_tasks_dir / "TASK-003.md").exists()

    def test_verify_timestamp_is_included(self, tmp_path, project_context):
        """Verify timestamp is included in task file."""
        before = datetime.now().replace(microsecond=0)
        create_task(project_context, "Test Task")
        after = datetime.now().replace(microsecond=0)
        
        mock_tasks_dir = tmp_path / ".ayder" / "tasks"
        content = (mock_tasks_dir / "TASK-001.md").read_text()
        
        # Extract timestamp
        match = re.search(r"- \*\*Created:\*\* (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", content)
        assert match is not None
        
        timestamp = datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S")
        assert before <= timestamp <= after

    def test_create_task_without_description(self, tmp_path, project_context):
        """Test that default description is used when not provided."""
        create_task(project_context, "Test Task")
        
        mock_tasks_dir = tmp_path / ".ayder" / "tasks"
        content = (mock_tasks_dir / "TASK-001.md").read_text()
        assert "No description provided." in content


class TestParseStatus:
    """Test _parse_status() function."""

    def test_extract_status_from_valid_task_file(self, tmp_path):
        """Test extracting status from valid task file."""
        mock_tasks_dir = tmp_path / ".ayder" / "tasks"
        mock_tasks_dir.mkdir(parents=True)
        
        task_content = """# Test Task

- **ID:** TASK-001
- **Status:** in_progress
- **Created:** 2024-01-01 12:00:00

## Description

Test description.
"""
        task_file = mock_tasks_dir / "TASK-001.md"
        task_file.write_text(task_content)
        
        status = _parse_status(str(task_file))
        assert status == "in_progress"

    def test_return_unknown_for_missing_status(self, tmp_path):
        """Test returning 'unknown' for missing status."""
        mock_tasks_dir = tmp_path / ".ayder" / "tasks"
        mock_tasks_dir.mkdir(parents=True)
        
        task_content = """# Test Task

- **ID:** TASK-001
- **Created:** 2024-01-01 12:00:00

## Description

Test description.
"""
        task_file = mock_tasks_dir / "TASK-001.md"
        task_file.write_text(task_content)
        
        status = _parse_status(str(task_file))
        assert status == "unknown"

    def test_error_handling_for_nonexistent_file(self, tmp_path):
        """Test error handling for non-existent file."""
        non_existent_file = str(tmp_path / "non_existent.md")
        
        status = _parse_status(non_existent_file)
        assert status == "unknown"

    def test_extract_different_status_values(self, tmp_path):
        """Test extracting different status values."""
        mock_tasks_dir = tmp_path / ".ayder" / "tasks"
        mock_tasks_dir.mkdir(parents=True)
        
        statuses = ["pending", "done", "in_progress", "blocked"]
        
        for i, status in enumerate(statuses, 1):
            task_content = f"""# Task {i}

- **ID:** TASK-{i:03d}
- **Status:** {status}
- **Created:** 2024-01-01 12:00:00

## Description

Test.
"""
            task_file = mock_tasks_dir / f"TASK-{i:03d}.md"
            task_file.write_text(task_content)
            
            extracted = _parse_status(str(task_file))
            assert extracted == status


class TestParseTitle:
    """Test _parse_title() function."""

    def test_extract_title_from_valid_task_file(self, tmp_path):
        """Test extracting title from valid task file."""
        mock_tasks_dir = tmp_path / ".ayder" / "tasks"
        mock_tasks_dir.mkdir(parents=True)
        
        task_content = """# My Awesome Task

- **ID:** TASK-001
- **Status:** pending

## Description

Test.
"""
        task_file = mock_tasks_dir / "TASK-001.md"
        task_file.write_text(task_content)
        
        title = _parse_title(str(task_file))
        assert title == "My Awesome Task"

    def test_return_filename_for_files_without_title(self, tmp_path):
        """Test returning filename for files without title."""
        mock_tasks_dir = tmp_path / ".ayder" / "tasks"
        mock_tasks_dir.mkdir(parents=True)
        
        task_content = """This file has no title

Just some content.
"""
        task_file = mock_tasks_dir / "TASK-001.md"
        task_file.write_text(task_content)
        
        title = _parse_title(str(task_file))
        assert title == "TASK-001.md"

    def test_error_handling(self, tmp_path):
        """Test error handling for non-existent file."""
        non_existent_file = str(tmp_path / "non_existent.md")
        
        title = _parse_title(non_existent_file)
        assert title == "non_existent.md"


class TestListTasks:
    """Test list_tasks() function."""

    def test_when_no_tasks_exist(self, tmp_path, project_context):
        """Test when no tasks exist."""
        result = list_tasks(project_context)
        assert isinstance(result, ToolSuccess)
        assert result == "No tasks found."

    def test_listing_multiple_tasks(self, tmp_path, project_context):
        """Test listing multiple tasks."""
        # Create tasks
        create_task(project_context, "First Task", "Description 1")
        create_task(project_context, "Second Task", "Description 2")
        
        result = list_tasks(project_context)
        
        # Check table contains both tasks
        assert "TASK-001" in result
        assert "First Task" in result
        assert "TASK-002" in result
        assert "Second Task" in result

    def test_task_name_truncation(self, tmp_path, project_context):
        """Test task name truncation for long titles."""
        # Create task with very long title
        long_title = "A" * 100
        create_task(project_context, long_title)
        
        result = list_tasks(project_context)
        
        # Check title is truncated (should contain ..)
        assert ".." in result or len(long_title) <= 72

    def test_table_formatting(self, tmp_path, project_context):
        """Verify table formatting."""
        create_task(project_context, "Test Task")
        
        result = list_tasks(project_context)
        
        # Check table structure
        assert "Task ID" in result
        assert "Task Name" in result
        assert "Status" in result
        assert "|" in result  # Table separator

    def test_sorting_by_id(self, tmp_path, project_context):
        """Test sorting by ID."""
        # Create tasks out of order
        create_task(project_context, "Third Task")  # Will be 001
        create_task(project_context, "Fourth Task")  # Will be 002
        
        result = list_tasks(project_context)
        
        # Find positions
        pos_001 = result.find("TASK-001")
        pos_002 = result.find("TASK-002")
        
        assert pos_001 < pos_002  # 001 should come before 002


class TestShowTask:
    """Test show_task() function."""

    def test_show_existing_task(self, tmp_path, project_context):
        """Test showing existing task."""
        create_task(project_context, "Test Task", "Test description")

        result = show_task(project_context, 1)

        assert isinstance(result, ToolSuccess)
        assert "# Test Task" in result
        assert "Test description" in result
        assert "TASK-001" in result

    def test_error_for_nonexistent_task(self, tmp_path, project_context):
        """Test error for non-existent task."""
        result = show_task(project_context, 999)

        assert isinstance(result, ToolError)
        assert "Error" in result
        assert "TASK-999" in result
        assert "not found" in result.lower()

    def test_string_task_id(self, tmp_path, project_context):
        """Test showing task with string ID."""
        create_task(project_context, "Test Task")
        
        result = show_task(project_context, "1")
        
        assert "# Test Task" in result


class TestUpdateTaskStatus:
    """Test _update_task_status() function."""

    def test_successful_status_update(self, tmp_path, project_context):
        """Test successful status update."""
        create_task(project_context, "Test Task")

        result = _update_task_status(project_context, 1, "done")

        assert result.is_success
        
        mock_tasks_dir = tmp_path / ".ayder" / "tasks"
        # Verify file was updated
        content = (mock_tasks_dir / "TASK-001.md").read_text()
        assert "- **Status:** done" in content

    def test_error_for_nonexistent_task(self, tmp_path, project_context):
        """Test error for non-existent task."""
        result = _update_task_status(project_context, 999, "done")
        
        assert "Error" in result
        assert "not found" in result.lower()

    def test_regex_replacement(self, tmp_path, project_context):
        """Verify regex replacement works correctly."""
        mock_tasks_dir = tmp_path / ".ayder" / "tasks"
        mock_tasks_dir.mkdir(parents=True)
        
        # Create task with custom status
        task_content = """# Test Task

- **ID:** TASK-001
- **Status:** custom_status
- **Created:** 2024-01-01 12:00:00

## Description

Test.
"""
        (mock_tasks_dir / "TASK-001.md").write_text(task_content)
        
        _update_task_status(project_context, 1, "new_status")
        
        content = (mock_tasks_dir / "TASK-001.md").read_text()
        assert "- **Status:** new_status" in content
        assert "custom_status" not in content

    def test_exception_during_file_write(self, tmp_path, monkeypatch, project_context):
        """Test exception handling during file write - Lines 175-176."""
        mock_tasks_dir = tmp_path / ".ayder" / "tasks"
        mock_tasks_dir.mkdir(parents=True)
        
        # Create task
        task_content = """# Test Task

- **ID:** TASK-001
- **Status:** pending
- **Created:** 2024-01-01 12:00:00

## Description

Test.
"""
        task_file = mock_tasks_dir / "TASK-001.md"
        task_file.write_text(task_content)
        
        # Mock write_text to raise an exception
        def mock_write_text(*args, **kwargs):
            raise PermissionError("Permission denied")
        
        monkeypatch.setattr(Path, "write_text", mock_write_text)
        
        result = _update_task_status(project_context, 1, "done")
        
        assert "Error" in result
        assert "Permission denied" in result


class TestImplementTask:
    """Test implement_task() function."""

    def test_implement_pending_task(self, tmp_path, project_context):
        """Test implementing pending task."""
        create_task(project_context, "Test Task", "Test description")
        
        result = implement_task(project_context, 1)
        
        assert "TASK-001" in result
        assert "ready to implement" in result.lower() or "marked" in result.lower()
        assert "Test description" in result

    def test_error_for_already_completed_task(self, tmp_path, project_context):
        """Test error for already completed task."""
        create_task(project_context, "Test Task")

        # First implementation
        implement_task(project_context, 1)

        # Second implementation should show already completed
        result = implement_task(project_context, 1)

        assert "already completed" in result.lower()

    def test_error_for_nonexistent_task(self, tmp_path, project_context):
        """Test error for non-existent task."""
        result = implement_task(project_context, 999)
        
        assert "Error" in result
        assert "not found" in result.lower()

    def test_status_updated_to_done(self, tmp_path, project_context):
        """Verify status is updated to 'done'."""
        create_task(project_context, "Test Task")
        
        mock_tasks_dir = tmp_path / ".ayder" / "tasks"
        # Verify initial status
        content = (mock_tasks_dir / "TASK-001.md").read_text()
        assert "- **Status:** pending" in content
        
        # Implement task
        implement_task(project_context, 1)
        
        # Verify status changed
        content = (mock_tasks_dir / "TASK-001.md").read_text()
        assert "- **Status:** done" in content

    def test_error_when_status_update_fails(self, tmp_path, monkeypatch, project_context):
        """Test error return when _update_task_status fails - Line 199."""
        create_task(project_context, "Test Task")
        
        # Mock _update_task_status to return an error
        # Note: we need to mock it in the module where it's called
        import ayder_cli.tasks as tasks
        
        # Save original function
        original = tasks._update_task_status
        
        try:
            tasks._update_task_status = lambda ctx, task_id, status: ToolError("Error: Failed to update")
            result = implement_task(project_context, 1)
        finally:
            tasks._update_task_status = original
        
        # Should return the error from _update_task_status
        assert "Error: Failed to update" in result


class TestImplementAllTasks:
    """Test implement_all_tasks() function."""

    def test_when_no_tasks_exist(self, tmp_path, project_context):
        """Test when no tasks exist."""
        result = implement_all_tasks(project_context)
        
        assert result == "No tasks found."

    def test_no_pending_tasks(self, tmp_path, project_context):
        """Test when no pending tasks."""
        # Create and complete a task
        create_task(project_context, "Completed Task")
        implement_task(project_context, 1)
        
        result = implement_all_tasks(project_context)
        
        assert "No pending tasks" in result

    def test_implement_multiple_pending_tasks(self, tmp_path, project_context):
        """Test implementing multiple pending tasks."""
        # Create multiple tasks
        create_task(project_context, "First Task")
        create_task(project_context, "Second Task")
        
        result = implement_all_tasks(project_context)
        
        assert "Found 2 pending task(s)" in result
        assert "TASK-001" in result
        assert "TASK-002" in result
        assert "First Task" in result
        assert "Second Task" in result

    def test_marks_tasks_as_done(self, tmp_path, project_context):
        """Test that tasks are marked as done."""
        create_task(project_context, "Test Task")
        
        implement_all_tasks(project_context)
        
        mock_tasks_dir = tmp_path / ".ayder" / "tasks"
        # Verify status changed
        content = (mock_tasks_dir / "TASK-001.md").read_text()
        assert "- **Status:** done" in content

    def test_skips_already_done_tasks(self, tmp_path, project_context):
        """Test that already done tasks are skipped."""
        # Create tasks, complete first one
        create_task(project_context, "First Task")
        create_task(project_context, "Second Task")
        implement_task(project_context, 1)  # Complete first task
        
        result = implement_all_tasks(project_context)
        
        # Should only process second task
        assert "Found 1 pending task(s)" in result
        assert "Second Task" in result