"""Tests for tool schemas."""

import pytest
from ayder_cli.tools import schemas


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

    def test_expected_tools_present(self):
        """Test that expected tools are present in schemas."""
        expected_tools = [
            "list_files",
            "read_file",
            "write_file",
            "replace_string",
            "run_shell_command",
            "search_codebase",
            "create_task",
            "show_task",
            "implement_task",
            "implement_all_tasks",
        ]
        names = [schema["function"]["name"] for schema in schemas.tools_schema]
        for tool in expected_tools:
            assert tool in names

    def test_parameter_properties_valid(self):
        """Test that parameter properties are valid."""
        for schema in schemas.tools_schema:
            params = schema["function"]["parameters"]
            assert "type" in params
            assert params["type"] == "object"
            assert "properties" in params
            assert isinstance(params["properties"], dict)
