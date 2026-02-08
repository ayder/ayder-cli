"""Additional coverage tests for tools/registry.py."""

import json
import pytest
from unittest.mock import Mock, patch
from ayder_cli.tools import registry
from ayder_cli.core.context import ProjectContext
from ayder_cli.core.result import ToolSuccess, ToolError


class TestToolRegistryExecute:
    """Test execute method edge cases."""

    def test_execute_with_json_string_arguments(self, tmp_path):
        """Lines 145-149: Execute with JSON string arguments."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        # Set up project context with tmp_path as root
        ctx = ProjectContext(str(tmp_path))
        reg = registry.ToolRegistry(ctx)
        
        # Mock the tool function
        mock_func = Mock(return_value="success")
        reg.register("read_file", mock_func)

        # Execute with JSON string
        args_json = json.dumps({"file_path": "test.txt"})
        result = reg.execute("read_file", args_json)

        assert result == "success"
        mock_func.assert_called_once()

    def test_execute_with_invalid_json_string(self, tmp_path):
        """Line 148-149: Invalid JSON string returns error."""
        ctx = ProjectContext(str(tmp_path))
        reg = registry.ToolRegistry(ctx)

        result = reg.execute("tool", "{invalid_json")
        assert isinstance(result, ToolError)
        assert result.category == "validation"
        assert "Invalid JSON arguments" in result

    def test_execute_unregistered_tool_in_definitions(self, tmp_path):
        """Tool in TOOL_DEFINITIONS but not registered returns error."""
        ctx = ProjectContext(str(tmp_path))
        reg = registry.ToolRegistry(ctx)

        # create_task is in TOOL_DEFINITIONS but not registered in this empty registry.
        # Validation passes (it's a known tool) but execution fails (not registered).
        result = reg.execute("create_task", {"title": "test"})
        assert isinstance(result, ToolError)
        assert result.category == "validation"
        assert "Error: Unknown tool" in result

    def test_execute_unknown_tool_not_in_schema(self, tmp_path):
        """Unknown tool not in schema fails validation."""
        ctx = ProjectContext(str(tmp_path))
        reg = registry.ToolRegistry(ctx)

        result = reg.execute("completely_unknown_tool", {})
        assert isinstance(result, ToolError)
        assert "Unknown tool" in result

    def test_execute_validation_error(self, tmp_path):
        """Lines 156-159: Validation error returns error message."""
        ctx = ProjectContext(str(tmp_path))
        reg = registry.ToolRegistry(ctx)

        # Use a real tool (read_file) but missing required args
        result = reg.execute("read_file", {})
        assert isinstance(result, ToolError)
        assert result.category == "validation"
        assert "Validation Error" in result or "Missing required parameter" in result

    def test_execute_with_dict_arguments(self, tmp_path):
        """Lines 150-151, 154: Execute with dict arguments."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        # Set up project context with tmp_path as root
        ctx = ProjectContext(str(tmp_path))
        reg = registry.ToolRegistry(ctx)
        
        mock_func = Mock(return_value="success")
        reg.register("read_file", mock_func)

        result = reg.execute("read_file", {"file_path": "test.txt"})
        assert result == "success"


class TestToolRegistryGetRegisteredTools:
    """Test get_registered_tools method."""

    def test_get_registered_tools_empty(self, tmp_path):
        """Line 176: Empty registry returns empty list."""
        ctx = ProjectContext(str(tmp_path))
        reg = registry.ToolRegistry(ctx)
        assert reg.get_registered_tools() == []

    def test_get_registered_tools_multiple(self, tmp_path):
        """Line 176: Registry with tools returns tool names."""
        ctx = ProjectContext(str(tmp_path))
        reg = registry.ToolRegistry(ctx)
        
        reg.register("tool1", lambda: None)
        reg.register("tool2", lambda: None)
        
        tools = reg.get_registered_tools()
        assert "tool1" in tools
        assert "tool2" in tools
        assert len(tools) == 2


class TestCreateDefaultRegistry:
    """Test create_default_registry function."""

    def test_create_default_registry_registers_all_tools(self, tmp_path):
        """Lines 188-218: All tools are registered."""
        ctx = ProjectContext(str(tmp_path))
        reg = registry.create_default_registry(ctx)
        
        tools = reg.get_registered_tools()
        expected_tools = [
            "list_files", "read_file", "write_file", "replace_string",
            "run_shell_command", "get_project_structure", "search_codebase"
        ]

        for tool in expected_tools:
            assert tool in tools

    def test_create_default_registry_executes_read_file(self, tmp_path):
        """Lines 188-218: Registry can execute read_file."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        # Set up project context with tmp_path as root
        ctx = ProjectContext(str(tmp_path))
        reg = registry.create_default_registry(ctx)

        result = reg.execute("read_file", {"file_path": "test.txt"})
        assert "test content" in result

    def test_create_default_registry_executes_list_files(self, tmp_path):
        """Lines 188-218: Registry can execute list_files."""
        (tmp_path / "file.txt").write_text("content")

        # Set up project context with tmp_path as root
        ctx = ProjectContext(str(tmp_path))
        reg = registry.create_default_registry(ctx)

        result = reg.execute("list_files", {"directory": "."})
        assert "file.txt" in result


class TestNormalizeToolArgumentsEdgeCases:
    """Test normalize_tool_arguments edge cases."""

    def test_normalize_with_empty_arguments(self, tmp_path):
        """Normalize with empty arguments."""
        ctx = ProjectContext(str(tmp_path))
        result = registry.normalize_tool_arguments("read_file", {}, ctx)
        assert result == {}

    def test_normalize_path_resolution(self, tmp_path):
        """Path parameters are resolved to absolute."""
        # Create a file to test with
        (tmp_path / "test.txt").write_text("content")

        # Set up project context with tmp_path as root
        ctx = ProjectContext(str(tmp_path))
        
        args = {"file_path": "test.txt"}
        normalized = registry.normalize_tool_arguments("read_file", args, ctx)
        
        assert normalized["file_path"] == str(tmp_path / "test.txt")

    def test_normalize_integer_type_coercion(self, tmp_path):
        """String integers are coerced to int."""
        # Set up project context with tmp_path as root
        ctx = ProjectContext(str(tmp_path))
        
        args = {"start_line": "10"}
        normalized = registry.normalize_tool_arguments("read_file", args, ctx)
        
        assert isinstance(normalized["start_line"], int)
        assert normalized["start_line"] == 10

    def test_normalize_invalid_integer_kept_as_string(self, tmp_path):
        """Invalid integer strings are kept as-is."""
        # Set up project context with tmp_path as root
        ctx = ProjectContext(str(tmp_path))
        
        args = {"start_line": "invalid"}
        normalized = registry.normalize_tool_arguments("read_file", args, ctx)
        
        assert normalized["start_line"] == "invalid"


class TestParameterAliases:
    """Test parameter aliasing."""

    def test_path_alias_for_read_file(self, tmp_path):
        """'path' is converted to 'file_path'."""
        # Set up project context with tmp_path as root
        ctx = ProjectContext(str(tmp_path))
        
        args = {"path": "test.txt"}
        normalized = registry.normalize_tool_arguments("read_file", args, ctx)
        
        assert "file_path" in normalized
        assert "path" not in normalized

    def test_filepath_alias_for_write_file(self, tmp_path):
        """'filepath' is converted to 'file_path'."""
        # Set up project context with tmp_path as root
        ctx = ProjectContext(str(tmp_path))
        
        args = {"filepath": "test.txt"}
        normalized = registry.normalize_tool_arguments("write_file", args, ctx)
        
        assert "file_path" in normalized
        assert "filepath" not in normalized

    def test_dir_alias_for_list_files(self, tmp_path):
        """'dir' is converted to 'directory'."""
        # Set up project context with tmp_path as root
        ctx = ProjectContext(str(tmp_path))

        args = {"dir": "."}
        normalized = registry.normalize_tool_arguments("list_files", args, ctx)

        assert "directory" in normalized
        assert "dir" not in normalized


class TestRegistrySchemas:
    """Test get_schemas and tool accessibility."""

    def test_get_schemas_returns_all_tools(self, tmp_path):
        """get_schemas() returns all tool schemas."""
        ctx = ProjectContext(str(tmp_path))
        reg = registry.ToolRegistry(ctx)
        schemas = reg.get_schemas()
        names = {s["function"]["name"] for s in schemas}
        assert "list_files" in names
        assert "write_file" in names
        assert "search_codebase" in names
        assert "get_project_structure" in names

    def test_validate_tool_call_all_tools_accessible(self):
        """validate_tool_call works for all tools."""
        # get_project_structure
        is_valid, error = registry.validate_tool_call("get_project_structure", {})
        assert is_valid
        assert error == ""

        # write_file
        is_valid, error = registry.validate_tool_call(
            "write_file", {"file_path": "test.txt", "content": "hi"}
        )
        assert is_valid
        assert error == ""


