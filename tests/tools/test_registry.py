"""Tests for tool registry and execution."""

import json
import pytest
from unittest.mock import patch, MagicMock
from ayder_cli.tools import registry
from ayder_cli.core.context import ProjectContext
from ayder_cli.core.result import ToolSuccess, ToolError


@pytest.fixture
def project_context(tmp_path):
    """Create a project context with tmp_path as root."""
    return ProjectContext(str(tmp_path))


@pytest.fixture
def tool_registry(project_context):
    """Create a ToolRegistry with the project context."""
    return registry.create_default_registry(project_context)


class TestExecuteToolCall:
    """Test execute() method of ToolRegistry."""

    def test_dispatch_list_files(self, tmp_path, tool_registry):
        """Test dispatch to list_files."""
        (tmp_path / "test.txt").write_text("content")

        result = tool_registry.execute("list_files", {"directory": "."})
        assert isinstance(result, ToolSuccess)
        files = json.loads(result)
        assert "test.txt" in files

    def test_dispatch_read_file(self, tmp_path, tool_registry):
        """Test dispatch to read_file."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        result = tool_registry.execute("read_file", {"file_path": "test.txt"})
        assert result == "test content"

    def test_dispatch_write_file(self, tmp_path, tool_registry):
        """Test dispatch to write_file."""
        test_file = tmp_path / "test.txt"

        result = tool_registry.execute(
            "write_file",
            {"file_path": "test.txt", "content": "new content"}
        )
        assert "Successfully wrote" in result
        assert test_file.read_text() == "new content"

    def test_dispatch_replace_string(self, tmp_path, tool_registry):
        """Test dispatch to replace_string."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("old text")

        result = tool_registry.execute(
            "replace_string",
            {"file_path": "test.txt", "old_string": "old", "new_string": "new"}
        )
        assert "Successfully replaced" in result

    def test_dispatch_run_shell_command(self, tool_registry):
        """Test dispatch to run_shell_command."""
        result = tool_registry.execute("run_shell_command", {"command": "echo hi"})
        assert "Exit Code: 0" in result

    def test_with_json_string_arguments(self, tmp_path, tool_registry):
        """Test with JSON string arguments."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        args_json = json.dumps({"file_path": "test.txt"})
        result = tool_registry.execute("read_file", args_json)
        assert result == "content"

    def test_with_dict_arguments(self, tmp_path, tool_registry):
        """Test with dict arguments."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        args_dict = {"file_path": "test.txt"}
        result = tool_registry.execute("read_file", args_dict)
        assert result == "content"

    def test_with_invalid_json_string(self, tool_registry):
        """Test with invalid JSON string (error case)."""
        result = tool_registry.execute("read_file", "{invalid json}")
        assert isinstance(result, ToolError)
        assert result.category == "validation"
        assert "Error: Invalid JSON arguments" in result

    def test_unknown_tool_name_handling(self, tool_registry):
        """Test unknown tool name handling."""
        result = tool_registry.execute("unknown_tool", {})
        assert isinstance(result, ToolError)
        assert result.category == "validation"
        assert "Error: Unknown tool" in result


class TestNormalizeToolArguments:
    """Tests for normalize_tool_arguments function."""

    def test_value_error_propagation_for_invalid_path(self, tmp_path, project_context):
        """Test ValueError propagation for paths outside sandbox - Lines 71-73."""
        # Try to access a path outside the project root
        with pytest.raises(ValueError) as exc_info:
            registry.normalize_tool_arguments(
                "read_file", 
                {"file_path": "/etc/passwd"}, 
                project_context
            )
        
        assert "outside" in str(exc_info.value).lower() or "sandbox" in str(exc_info.value).lower()

    def test_type_coercion_value_error_handling(self, tmp_path, project_context):
        """Test ValueError handling during type coercion - Lines 81-82."""
        (tmp_path / "test.txt").write_text("content")
        
        # Pass a non-numeric string for start_line - should keep as string
        result = registry.normalize_tool_arguments(
            "read_file", 
            {"file_path": "test.txt", "start_line": "not_a_number"},
            project_context
        )
        
        # Should keep the original string value (not raise)
        assert result["start_line"] == "not_a_number"


class TestResolveFuncRef:
    """Tests for _resolve_func_ref() dynamic import function."""

    def test_resolves_valid_reference(self):
        """Test resolving a valid module:function reference."""
        func = registry._resolve_func_ref("ayder_cli.tools.impl:read_file")
        from ayder_cli.tools.impl import read_file
        assert func is read_file

    def test_resolves_external_module(self):
        """Test resolving a function from a non-tools module."""
        func = registry._resolve_func_ref("ayder_cli.notes:create_note")
        from ayder_cli.notes import create_note
        assert func is create_note

    def test_invalid_module_raises_import_error(self):
        """Test that a nonexistent module raises ImportError."""
        with pytest.raises(ModuleNotFoundError):
            registry._resolve_func_ref("nonexistent.module:func")

    def test_invalid_function_raises_attribute_error(self):
        """Test that a nonexistent function raises AttributeError."""
        with pytest.raises(AttributeError):
            registry._resolve_func_ref("ayder_cli.tools.impl:nonexistent_func")

    def test_missing_colon_raises_value_error(self):
        """Test that a reference without colon raises ValueError."""
        with pytest.raises(ValueError):
            registry._resolve_func_ref("ayder_cli.tools.impl.read_file")


class TestCreateDefaultRegistryAutoDiscovery:
    """Tests for auto-discovery via func_ref in create_default_registry."""

    def test_registers_all_25_tools(self, project_context):
        """Test that all 25 TOOL_DEFINITIONS are registered."""
        reg = registry.create_default_registry(project_context)
        assert len(reg.get_registered_tools()) == 25

    def test_registered_names_match_definitions(self, project_context):
        """Test that registered tool names match TOOL_DEFINITIONS names."""
        from ayder_cli.tools.definition import TOOL_DEFINITIONS
        reg = registry.create_default_registry(project_context)
        registered = set(reg.get_registered_tools())
        expected = {td.name for td in TOOL_DEFINITIONS}
        assert registered == expected

    def test_all_func_refs_resolve_to_callables(self, project_context):
        """Test that every func_ref resolves to a callable."""
        from ayder_cli.tools.definition import TOOL_DEFINITIONS
        for td in TOOL_DEFINITIONS:
            func = registry._resolve_func_ref(td.func_ref)
            assert callable(func), f"{td.name} func_ref does not resolve to callable"


class TestToolRegistryUnknownTool:
    """Tests for ToolRegistry with unknown tools."""

    def test_tool_registry_execute_non_task_unknown_tool(self, tmp_path, project_context):
        """Test unknown non-task tool in registry execution."""
        # Create a fresh registry without any tools registered
        fresh_registry = registry.ToolRegistry(project_context)

        # Try to execute an unregistered tool
        result = fresh_registry.execute("unregistered_tool", {})
        assert "Error: Unknown tool" in result
