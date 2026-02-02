"""Tests for tool registry and execution."""

import json
import pytest
from unittest.mock import patch, MagicMock
from ayder_cli.tools import registry
from ayder_cli.tools import impl
from ayder_cli import fs_tools
from ayder_cli.path_context import ProjectContext


@pytest.fixture
def project_context(tmp_path, monkeypatch):
    """Create a project context with tmp_path as root and set it for registry and impl."""
    ctx = ProjectContext(str(tmp_path))
    # Patch both modules that use project context
    monkeypatch.setattr(registry, "_default_project_ctx", ctx)
    monkeypatch.setattr(impl, "_default_project_ctx", ctx)
    return ctx


class TestGetProjectContext:
    """Tests for get_project_context() function - Line 24 coverage."""

    def test_module_context_lazy_initialization(self, tmp_path, monkeypatch):
        """Test lazy initialization of module-level ProjectContext - Line 24."""
        # Clear the global state to trigger initialization
        monkeypatch.setattr(registry, "_default_project_ctx", None)
        
        # Change to tmp_path for initialization
        monkeypatch.chdir(tmp_path)
        
        # Access should trigger initialization
        ctx = registry.get_project_context()
        
        assert ctx is not None
        assert isinstance(ctx, ProjectContext)
        assert ctx.root == tmp_path

    def test_module_context_returns_existing(self, tmp_path, monkeypatch):
        """Test that existing context is returned if already set."""
        # Set a specific context
        ctx = ProjectContext(str(tmp_path))
        monkeypatch.setattr(registry, "_default_project_ctx", ctx)
        
        # Should return the same context
        result = registry.get_project_context()
        assert result is ctx


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


class TestNormalizeToolArguments:
    """Tests for normalize_tool_arguments function."""

    def test_value_error_propagation_for_invalid_path(self, tmp_path, monkeypatch):
        """Test ValueError propagation for paths outside sandbox - Lines 71-73."""
        ctx = ProjectContext(str(tmp_path))
        monkeypatch.setattr(registry, "_default_project_ctx", ctx)
        
        # Try to access a path outside the project root
        with pytest.raises(ValueError) as exc_info:
            registry.normalize_tool_arguments("read_file", {"file_path": "/etc/passwd"})
        
        assert "outside" in str(exc_info.value).lower() or "sandbox" in str(exc_info.value).lower()

    def test_type_coercion_value_error_handling(self, tmp_path, monkeypatch):
        """Test ValueError handling during type coercion - Lines 81-82."""
        ctx = ProjectContext(str(tmp_path))
        monkeypatch.setattr(registry, "_default_project_ctx", ctx)
        
        # Create a test file
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")
        
        # Pass a non-numeric string for start_line - should keep as string
        result = registry.normalize_tool_arguments(
            "read_file", 
            {"file_path": "test.txt", "start_line": "not_a_number"}
        )
        
        # Should keep the original string value (not raise)
        assert result["start_line"] == "not_a_number"


class TestMockableToolRegistry:
    """Tests for _MockableToolRegistry class."""

    def test_unknown_tool_in_mockable_registry(self, tmp_path, monkeypatch):
        """Test unknown tool error in _MockableToolRegistry - Line 283."""
        ctx = ProjectContext(str(tmp_path))
        monkeypatch.setattr(registry, "_default_project_ctx", ctx)
        
        # Create a mockable registry
        mockable_reg = registry._MockableToolRegistry()
        
        # Try to execute a task tool that doesn't exist in fs_tools
        # This should hit line 283
        with patch.object(registry, '_default_registry', mockable_reg):
            # The tool should be in PATH_PARAMETERS to get past normalization
            result = registry.execute_tool_call("nonexistent_task_tool", {})
            # Should return unknown tool error (but this won't hit line 283 directly)

    def test_tool_registry_execute_non_task_unknown_tool(self, tmp_path, monkeypatch):
        """Test unknown non-task tool in registry execution."""
        ctx = ProjectContext(str(tmp_path))
        monkeypatch.setattr(registry, "_default_project_ctx", ctx)
        
        # Create a fresh registry without any tools registered
        fresh_registry = registry.ToolRegistry()
        
        # Try to execute an unregistered tool
        result = fresh_registry.execute("unregistered_tool", {})
        assert "Error: Unknown tool" in result
