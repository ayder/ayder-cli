"""Tests for tool schemas."""

from ayder_cli.tools import schemas
from ayder_cli.tools.definition import ToolDefinition


class TestToolSchemas:
    """Test tool schema definitions."""

    def test_tools_schema_is_list(self):
        """Test that tools_schema is a list."""
        assert isinstance(schemas.tools_schema, list)

    def test_tools_schema_not_empty(self):
        """Test that tools_schema is not empty."""
        assert len(schemas.tools_schema) > 0

    def test_all_schemas_have_required_fields(self):
        """Test that all schemas have required fields."""
        required_fields = {"type", "function"}
        for schema in schemas.tools_schema:
            assert required_fields.issubset(schema.keys())
            assert schema["type"] == "function"
            assert "name" in schema["function"]
            assert "description" in schema["function"]
            assert "parameters" in schema["function"]

    def test_schema_names_are_unique(self):
        """Test that all schema names are unique."""
        names = [schema["function"]["name"] for schema in schemas.tools_schema]
        assert len(names) == len(set(names))

    def test_parameter_properties_valid(self):
        """Test that parameter properties are valid."""
        for schema in schemas.tools_schema:
            params = schema["function"]["parameters"]
            assert "type" in params
            assert params["type"] == "object"
            assert "properties" in params
            assert isinstance(params["properties"], dict)


class TestToolDefinitions:
    """Test tool definition properties."""

    def test_all_tools_in_schema(self):
        """Verify tools_schema contains all defined tools."""
        expected_tools = {
            "list_files", "read_file", "write_file", "replace_string",
            "run_shell_command", "search_codebase", "get_project_structure",
            "insert_line", "delete_line", "get_file_info",
            "create_note", "save_memory", "load_memory",
            "run_background_process", "get_background_output",
            "kill_background_process", "list_background_processes",
            "list_tasks", "show_task",
            "manage_environment_vars",
            "create_virtualenv", "install_requirements",
            "list_virtualenvs", "activate_virtualenv", "remove_virtualenv",
            "temporal_workflow",
            "fetch_web",
            "python_editor",
        }
        names = {s["function"]["name"] for s in schemas.tools_schema}
        assert names == expected_tools

    def test_no_exposed_to_llm_field(self):
        """Verify exposed_to_llm attribute no longer exists on ToolDefinition."""
        assert not hasattr(ToolDefinition, "exposed_to_llm")
        # Also check field names in the dataclass
        field_names = {f.name for f in ToolDefinition.__dataclass_fields__.values()}
        assert "exposed_to_llm" not in field_names

