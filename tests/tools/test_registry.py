"""Tests for tool registry and execution."""

import json
import pytest
from unittest.mock import patch
from ayder_cli.tools import registry
from ayder_cli.tools import impl
from ayder_cli import fs_tools


@pytest.fixture
def project_context(tmp_path, monkeypatch):
    """Create a project context with tmp_path as root and set it for registry and impl."""
    from ayder_cli.path_context import ProjectContext
    
    ctx = ProjectContext(str(tmp_path))
    # Patch both modules that use project context
    monkeypatch.setattr(registry, "_default_project_ctx", ctx)
    monkeypatch.setattr(impl, "_default_project_ctx", ctx)
    return ctx


class TestExecuteToolCall:
    """Test execute_tool_call() dispatcher."""

    def test_dispatch_list_files(self, tmp_path, project_context):
        """Test dispatch to list_files."""
        (tmp_path / "test.txt").write_text("content")

        result = registry.execute_tool_call("list_files", {"directory": "."})
        files = json.loads(result)
        assert "test.txt" in files

    def test_dispatch_read_file(self, tmp_path, project_context):
        """Test dispatch to read_file."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        result = registry.execute_tool_call("read_file", {"file_path": "test.txt"})
        assert result == "test content"

    def test_dispatch_write_file(self, tmp_path, project_context):
        """Test dispatch to write_file."""
        test_file = tmp_path / "test.txt"

        result = registry.execute_tool_call(
            "write_file",
            {"file_path": "test.txt", "content": "new content"}
        )
        assert "Successfully wrote" in result
        assert test_file.read_text() == "new content"

    def test_dispatch_replace_string(self, tmp_path, project_context):
        """Test dispatch to replace_string."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("old text")

        result = registry.execute_tool_call(
            "replace_string",
            {"file_path": "test.txt", "old_string": "old", "new_string": "new"}
        )
        assert "Successfully replaced" in result

    def test_dispatch_run_shell_command(self, project_context):
        """Test dispatch to run_shell_command."""
        result = registry.execute_tool_call("run_shell_command", {"command": "echo hi"})
        assert "Exit Code: 0" in result

    def test_with_json_string_arguments(self, tmp_path, project_context):
        """Test with JSON string arguments."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        args_json = json.dumps({"file_path": "test.txt"})
        result = registry.execute_tool_call("read_file", args_json)
        assert result == "content"

    def test_with_dict_arguments(self, tmp_path, project_context):
        """Test with dict arguments."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        args_dict = {"file_path": "test.txt"}
        result = registry.execute_tool_call("read_file", args_dict)
        assert result == "content"

    def test_with_invalid_json_string(self):
        """Test with invalid JSON string (error case)."""
        result = registry.execute_tool_call("read_file", "{invalid json}")
        assert "Error: Invalid JSON arguments" in result

    def test_unknown_tool_name_handling(self):
        """Test unknown tool name handling."""
        result = registry.execute_tool_call("unknown_tool", {})
        assert "Error: Unknown tool" in result

    @patch('ayder_cli.fs_tools.create_task')
    def test_dispatch_create_task(self, mock_create_task):
        """Test dispatch to create_task."""
        mock_create_task.return_value = "Task created"
        result = registry.execute_tool_call("create_task", {"title": "Test Task"})
        assert result == "Task created"
        mock_create_task.assert_called_once_with(title="Test Task")

    @patch('ayder_cli.fs_tools.show_task')
    def test_dispatch_show_task(self, mock_show_task):
        """Test dispatch to show_task."""
        mock_show_task.return_value = "Task details"
        result = registry.execute_tool_call("show_task", {"task_id": 1})
        assert result == "Task details"
        mock_show_task.assert_called_once_with(task_id=1)

    @patch('ayder_cli.fs_tools.implement_task')
    def test_dispatch_implement_task(self, mock_implement_task):
        """Test dispatch to implement_task."""
        mock_implement_task.return_value = "Task implemented"
        result = registry.execute_tool_call("implement_task", {"task_id": 1})
        assert result == "Task implemented"
        mock_implement_task.assert_called_once_with(task_id=1)

    @patch('ayder_cli.fs_tools.implement_all_tasks')
    def test_dispatch_implement_all_tasks(self, mock_implement_all):
        """Test dispatch to implement_all_tasks."""
        mock_implement_all.return_value = "All tasks done"
        result = registry.execute_tool_call("implement_all_tasks", {})
        assert result == "All tasks done"
        mock_implement_all.assert_called_once()
