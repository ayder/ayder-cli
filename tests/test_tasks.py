"""Tests for task management functionality in tasks.py."""

import pytest
from pathlib import Path
from ayder_cli.tasks import list_tasks, show_task, create_task
from ayder_cli.core.context import ProjectContext
from ayder_cli.core.result import ToolSuccess, ToolError


@pytest.fixture
def project_context(tmp_path):
    """Create a project context with tmp_path as root."""
    return ProjectContext(str(tmp_path))


@pytest.fixture
def tasks_dir(tmp_path):
    """Create tasks directory and return path."""
    tasks = tmp_path / ".ayder" / "tasks"
    tasks.mkdir(parents=True)
    return tasks


class TestListTasks:
    """Tests for list_tasks function."""

    def test_list_tasks_empty(self, project_context):
        """Test listing tasks when directory is empty."""
        result = list_tasks(project_context)
        assert isinstance(result, ToolSuccess)
        assert "No tasks found" in result

    def test_list_tasks_format_list(self, project_context, tasks_dir):
        """Test list format returns relative paths (pending only by default)."""
        # Create test tasks
        (tasks_dir / "TASK-001-first.md").write_text("# First\n- **ID:** TASK-001\n- **Status:** pending\n")
        (tasks_dir / "TASK-002-second.md").write_text("# Second\n- **ID:** TASK-002\n- **Status:** done\n")

        # Default: pending only
        result = list_tasks(project_context, format="list")
        assert isinstance(result, ToolSuccess)
        assert ".ayder/tasks/TASK-001-first.md" in result
        assert ".ayder/tasks/TASK-002-second.md" not in result

        # All tasks
        result = list_tasks(project_context, format="list", status="all")
        assert isinstance(result, ToolSuccess)
        assert ".ayder/tasks/TASK-001-first.md" in result
        assert ".ayder/tasks/TASK-002-second.md" in result
        lines = result.strip().split("\n")
        assert len(lines) == 2

    def test_list_tasks_format_table(self, project_context, tasks_dir):
        """Test table format returns formatted table."""
        # Create test tasks
        (tasks_dir / "TASK-001-first.md").write_text("# First Task\n- **ID:** TASK-001\n- **Status:** pending\n")
        (tasks_dir / "TASK-002-second.md").write_text("# Second Task\n- **ID:** TASK-002\n- **Status:** done\n")

        # Default: pending only
        result = list_tasks(project_context, format="table")
        assert isinstance(result, ToolSuccess)
        assert "TASK-001" in result
        assert "First Task" in result
        assert "TASK-002" not in result
        assert "Second Task" not in result

        # All tasks
        result = list_tasks(project_context, format="table", status="all")
        assert isinstance(result, ToolSuccess)
        # Should contain table headers
        assert "Task ID" in result
        assert "Task Name" in result
        assert "Status" in result
        # Should contain task data
        assert "TASK-001" in result
        assert "TASK-002" in result
        assert "First Task" in result
        assert "Second Task" in result

    def test_list_tasks_default_format(self, project_context, tasks_dir):
        """Test default format is 'list'."""
        (tasks_dir / "TASK-001-test.md").write_text("# Test\n- **ID:** TASK-001\n- **Status:** pending\n")

        result = list_tasks(project_context)
        assert isinstance(result, ToolSuccess)
        # Default should be list format (relative paths)
        assert ".ayder/tasks/TASK-001-test.md" in result

    def test_list_tasks_sorted_by_id(self, project_context, tasks_dir):
        """Test tasks are sorted by ID."""
        # Create in reverse order
        (tasks_dir / "TASK-003-third.md").write_text("# Third\n- **ID:** TASK-003\n- **Status:** pending\n")
        (tasks_dir / "TASK-001-first.md").write_text("# First\n- **ID:** TASK-001\n- **Status:** pending\n")
        (tasks_dir / "TASK-002-second.md").write_text("# Second\n- **ID:** TASK-002\n- **Status:** pending\n")

        result = list_tasks(project_context, format="list")
        lines = result.strip().split("\n")

        assert "TASK-001" in lines[0]
        assert "TASK-002" in lines[1]
        assert "TASK-003" in lines[2]

    def test_list_tasks_status_pending(self, project_context, tasks_dir):
        """Test filtering by pending status (default)."""
        (tasks_dir / "TASK-001-pending.md").write_text("# Pending\n- **ID:** TASK-001\n- **Status:** pending\n")
        (tasks_dir / "TASK-002-done.md").write_text("# Done\n- **ID:** TASK-002\n- **Status:** done\n")
        (tasks_dir / "TASK-003-pending.md").write_text("# Also Pending\n- **ID:** TASK-003\n- **Status:** pending\n")

        result = list_tasks(project_context, format="list", status="pending")
        assert isinstance(result, ToolSuccess)
        assert "TASK-001-pending.md" in result
        assert "TASK-003-pending.md" in result
        assert "TASK-002-done.md" not in result

        lines = result.strip().split("\n")
        assert len(lines) == 2

    def test_list_tasks_status_done(self, project_context, tasks_dir):
        """Test filtering by done status."""
        (tasks_dir / "TASK-001-pending.md").write_text("# Pending\n- **ID:** TASK-001\n- **Status:** pending\n")
        (tasks_dir / "TASK-002-done.md").write_text("# Done\n- **ID:** TASK-002\n- **Status:** done\n")
        (tasks_dir / "TASK-003-done.md").write_text("# Also Done\n- **ID:** TASK-003\n- **Status:** done\n")

        result = list_tasks(project_context, format="list", status="done")
        assert isinstance(result, ToolSuccess)
        assert "TASK-002-done.md" in result
        assert "TASK-003-done.md" in result
        assert "TASK-001-pending.md" not in result

        lines = result.strip().split("\n")
        assert len(lines) == 2

    def test_list_tasks_status_all(self, project_context, tasks_dir):
        """Test showing all tasks regardless of status."""
        (tasks_dir / "TASK-001-pending.md").write_text("# Pending\n- **ID:** TASK-001\n- **Status:** pending\n")
        (tasks_dir / "TASK-002-done.md").write_text("# Done\n- **ID:** TASK-002\n- **Status:** done\n")

        result = list_tasks(project_context, format="list", status="all")
        assert isinstance(result, ToolSuccess)
        assert "TASK-001-pending.md" in result
        assert "TASK-002-done.md" in result

        lines = result.strip().split("\n")
        assert len(lines) == 2

    def test_list_tasks_no_pending_tasks(self, project_context, tasks_dir):
        """Test message when no pending tasks found."""
        (tasks_dir / "TASK-001-done.md").write_text("# Done\n- **ID:** TASK-001\n- **Status:** done\n")

        result = list_tasks(project_context, format="list")
        assert isinstance(result, ToolSuccess)
        assert "No tasks found with status 'pending'" in result

    def test_list_tasks_no_done_tasks(self, project_context, tasks_dir):
        """Test message when no done tasks found."""
        (tasks_dir / "TASK-001-pending.md").write_text("# Pending\n- **ID:** TASK-001\n- **Status:** pending\n")

        result = list_tasks(project_context, format="list", status="done")
        assert isinstance(result, ToolSuccess)
        assert "No tasks found with status 'done'" in result


class TestShowTask:
    """Tests for show_task function."""

    def test_show_task_by_relative_path(self, project_context, tasks_dir):
        """Test showing task by relative path."""
        content = "# Test Task\n- **ID:** TASK-001\n- **Status:** pending\n\nTest content"
        (tasks_dir / "TASK-001-test.md").write_text(content)

        result = show_task(project_context, ".ayder/tasks/TASK-001-test.md")
        assert isinstance(result, ToolSuccess)
        assert "Test Task" in result
        assert "Test content" in result

    def test_show_task_by_filename(self, project_context, tasks_dir):
        """Test showing task by filename."""
        content = "# Test Task\n- **ID:** TASK-001\n- **Status:** pending\n\nTest content"
        (tasks_dir / "TASK-001-test.md").write_text(content)

        result = show_task(project_context, "TASK-001-test.md")
        assert isinstance(result, ToolSuccess)
        assert "Test Task" in result

    def test_show_task_by_numeric_id(self, project_context, tasks_dir):
        """Test showing task by numeric ID."""
        content = "# Test Task\n- **ID:** TASK-001\n- **Status:** pending\n\nTest content"
        (tasks_dir / "TASK-001-test.md").write_text(content)

        # Try various ID formats
        for identifier in ["001", "1", "TASK-001"]:
            result = show_task(project_context, identifier)
            assert isinstance(result, ToolSuccess), f"Failed with identifier: {identifier}"
            assert "Test Task" in result

    def test_show_task_by_slug(self, project_context, tasks_dir):
        """Test showing task by slug match."""
        content = "# Test Task\n- **ID:** TASK-001\n- **Status:** pending\n\nTest content"
        (tasks_dir / "TASK-001-add-auth.md").write_text(content)

        result = show_task(project_context, "add-auth")
        assert isinstance(result, ToolSuccess)
        assert "Test Task" in result

    def test_show_task_partial_slug_match(self, project_context, tasks_dir):
        """Test showing task by partial slug match."""
        content = "# Test Task\n- **ID:** TASK-001\n- **Status:** pending\n\nTest content"
        (tasks_dir / "TASK-001-add-authentication.md").write_text(content)

        result = show_task(project_context, "auth")
        assert isinstance(result, ToolSuccess)
        assert "Test Task" in result

    def test_show_task_not_found(self, project_context, tasks_dir):
        """Test error when task not found."""
        result = show_task(project_context, "nonexistent")
        assert isinstance(result, ToolError)
        assert "not found" in result.lower()

    def test_show_task_legacy_format(self, project_context, tasks_dir):
        """Test showing task with legacy filename format."""
        content = "# Legacy Task\n- **ID:** TASK-001\n- **Status:** pending\n\nLegacy content"
        (tasks_dir / "TASK-001.md").write_text(content)

        result = show_task(project_context, "001")
        assert isinstance(result, ToolSuccess)
        assert "Legacy Task" in result

    def test_show_task_prioritizes_exact_path(self, project_context, tasks_dir):
        """Test that exact path match is prioritized over other strategies."""
        content1 = "# First Task\n- **ID:** TASK-001\n- **Status:** pending\n"
        content2 = "# Second Task\n- **ID:** TASK-002\n- **Status:** pending\n"

        (tasks_dir / "TASK-001-test.md").write_text(content1)
        (tasks_dir / "TASK-002-test.md").write_text(content2)

        # Request by exact filename should get that file, not slug match
        result = show_task(project_context, "TASK-001-test.md")
        assert "First Task" in result
        assert "Second Task" not in result


class TestCreateTaskIntegration:
    """Integration tests for task creation and listing/showing."""

    def test_create_and_list(self, project_context):
        """Test creating tasks and listing them."""
        create_task(project_context, "First Task", "Description 1")
        create_task(project_context, "Second Task", "Description 2")

        # Both tasks are pending by default
        result = list_tasks(project_context, format="list")
        assert ".ayder/tasks/TASK-001-first-task.md" in result
        assert ".ayder/tasks/TASK-002-second-task.md" in result

        # Using status="all" should also show them
        result = list_tasks(project_context, format="list", status="all")
        assert ".ayder/tasks/TASK-001-first-task.md" in result
        assert ".ayder/tasks/TASK-002-second-task.md" in result

    def test_create_and_show(self, project_context):
        """Test creating a task and showing it."""
        create_task(project_context, "Test Task", "Test description")

        result = show_task(project_context, "001")
        assert isinstance(result, ToolSuccess)
        assert "Test Task" in result
        assert "Test description" in result
