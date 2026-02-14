"""
Tests for tool definition auto-discovery system.

Phase 1 tests: Infrastructure validation without requiring actual definition files.
"""

import pytest
from unittest.mock import patch, MagicMock
import importlib

from ayder_cli.tools.definition import (
    ToolDefinition,
    _discover_definitions,
    TOOL_DEFINITIONS,
    TOOL_DEFINITIONS_BY_NAME,
)


class TestDiscoveryFunctionExists:
    """Test that discovery infrastructure exists and is callable."""

    def test_discover_definitions_function_exists(self):
        """Test that _discover_definitions function exists."""
        assert callable(_discover_definitions)

    def test_discover_definitions_has_docstring(self):
        """Test that discovery function is documented."""
        assert _discover_definitions.__doc__ is not None
        assert "Auto-discover" in _discover_definitions.__doc__

    def test_tool_definition_class_exists(self):
        """Test that ToolDefinition class exists."""
        assert ToolDefinition is not None

    def test_tool_definitions_exists(self):
        """Test that TOOL_DEFINITIONS tuple exists."""
        assert TOOL_DEFINITIONS is not None
        assert isinstance(TOOL_DEFINITIONS, tuple)

    def test_tool_definitions_by_name_exists(self):
        """Test that TOOL_DEFINITIONS_BY_NAME dict exists."""
        assert TOOL_DEFINITIONS_BY_NAME is not None
        assert isinstance(TOOL_DEFINITIONS_BY_NAME, dict)


class TestDiscoveryValidationLogic:
    """Test validation logic in discovery (using mocks, no real files needed)."""

    def test_duplicate_detection_logic(self):
        """Test that duplicate tool names would be detected."""
        # Create two tool definitions with same name
        mock_td1 = ToolDefinition(
            name="duplicate_tool",
            description="First definition",
            parameters={"type": "object", "properties": {}},
        )
        mock_td2 = ToolDefinition(
            name="duplicate_tool",
            description="Second definition",
            parameters={"type": "object", "properties": {}},
        )
        
        # Mock pkgutil.iter_modules to simulate two modules with duplicate tools
        with patch('ayder_cli.tools.definition.pkgutil.iter_modules') as mock_iter:
            mock_iter.return_value = [
                (MagicMock(), 'module1_definitions', False),
                (MagicMock(), 'module2_definitions', False),
            ]
            
            with patch('importlib.import_module') as mock_import:
                mock_module1 = MagicMock()
                mock_module1.TOOL_DEFINITIONS = [mock_td1]
                
                mock_module2 = MagicMock()
                mock_module2.TOOL_DEFINITIONS = [mock_td2]
                
                mock_import.side_effect = [mock_module1, mock_module2]
                
                # Should raise ValueError for duplicate
                with pytest.raises(ValueError, match="Duplicate tool name"):
                    _discover_definitions()

    def test_missing_required_tools_validation(self):
        """Test that missing required tools would be detected."""
        # Mock discovery to return tools without required ones
        mock_td = ToolDefinition(
            name="some_other_tool",
            description="Not a required tool",
            parameters={"type": "object", "properties": {}},
        )
        
        with patch('ayder_cli.tools.definition.pkgutil.iter_modules') as mock_iter:
            mock_iter.return_value = [(MagicMock(), 'module_definitions', False)]
            
            with patch('importlib.import_module') as mock_import:
                mock_module = MagicMock()
                mock_module.TOOL_DEFINITIONS = [mock_td]
                mock_import.return_value = mock_module
                
                # Should raise ImportError for missing required tools
                with pytest.raises(ImportError, match="Required core tools missing"):
                    _discover_definitions()

    def test_successful_discovery_with_mocks(self):
        """Test successful discovery with properly mocked modules."""
        # Create valid tool definitions including required ones
        tools = [
            ToolDefinition(
                name="list_files",
                description="List files",
                parameters={"type": "object", "properties": {}},
            ),
            ToolDefinition(
                name="read_file",
                description="Read file",
                parameters={"type": "object", "properties": {}},
            ),
            ToolDefinition(
                name="write_file",
                description="Write file",
                parameters={"type": "object", "properties": {}},
            ),
            ToolDefinition(
                name="run_shell_command",
                description="Run shell command",
                parameters={"type": "object", "properties": {}},
            ),
        ]
        
        with patch('ayder_cli.tools.definition.pkgutil.iter_modules') as mock_iter:
            mock_iter.return_value = [(MagicMock(), 'test_definitions', False)]
            
            with patch('importlib.import_module') as mock_import:
                mock_module = MagicMock()
                mock_module.TOOL_DEFINITIONS = tools
                mock_import.return_value = mock_module
                
                # Should succeed and return tuple of tools
                result = _discover_definitions()
                
                assert isinstance(result, tuple)
                assert len(result) == 4
                assert all(isinstance(td, ToolDefinition) for td in result)


class TestDiscoveryErrorHandling:
    """Test error handling in discovery."""

    def test_handles_missing_module_gracefully(self):
        """Test that modules without TOOL_DEFINITIONS are skipped."""
        # Create valid tools
        tools = [
            ToolDefinition(
                name="list_files",
                description="List files",
                parameters={"type": "object", "properties": {}},
            ),
            ToolDefinition(
                name="read_file",
                description="Read file",
                parameters={"type": "object", "properties": {}},
            ),
            ToolDefinition(
                name="write_file",
                description="Write file",
                parameters={"type": "object", "properties": {}},
            ),
            ToolDefinition(
                name="run_shell_command",
                description="Run shell command",
                parameters={"type": "object", "properties": {}},
            ),
        ]
        
        with patch('ayder_cli.tools.definition.pkgutil.iter_modules') as mock_iter:
            # One module with definitions, one without
            # Note: module names must end with '_definitions' to be processed
            mock_iter.return_value = [
                (MagicMock(), 'module_with_definitions', False),
                (MagicMock(), 'module_without_definitions', False),
            ]
            
            with patch('importlib.import_module') as mock_import:
                # Module with definitions
                mock_module_with = MagicMock()
                mock_module_with.TOOL_DEFINITIONS = tools
                
                # Module without TOOL_DEFINITIONS attribute
                mock_module_without = MagicMock(spec=[])
                
                mock_import.side_effect = [mock_module_with, mock_module_without]
                
                # Should work and only include tools from the valid module
                definitions = _discover_definitions()
                assert len(definitions) == 4

    def test_handles_import_error_gracefully(self):
        """Test that ImportError during module import is handled."""
        tools = [
            ToolDefinition(
                name="list_files",
                description="List files",
                parameters={"type": "object", "properties": {}},
            ),
            ToolDefinition(
                name="read_file",
                description="Read file",
                parameters={"type": "object", "properties": {}},
            ),
            ToolDefinition(
                name="write_file",
                description="Write file",
                parameters={"type": "object", "properties": {}},
            ),
            ToolDefinition(
                name="run_shell_command",
                description="Run shell command",
                parameters={"type": "object", "properties": {}},
            ),
        ]
        
        with patch('ayder_cli.tools.definition.pkgutil.iter_modules') as mock_iter:
            # Two modules: one raises ImportError, one succeeds
            # Note: module names must end with '_definitions' to be processed
            mock_iter.return_value = [
                (MagicMock(), 'bad_definitions', False),
                (MagicMock(), 'good_definitions', False),
            ]
            
            with patch('importlib.import_module') as mock_import:
                # First import raises error
                # Second import succeeds
                mock_good_module = MagicMock()
                mock_good_module.TOOL_DEFINITIONS = tools
                
                mock_import.side_effect = [
                    ImportError("Module not found"),
                    mock_good_module
                ]
                
                # Should handle error gracefully and return good tools
                definitions = _discover_definitions()
                assert len(definitions) == 4


class TestBackwardCompatibility:
    """Test that backward compatibility is maintained."""

    def test_tool_definitions_populated(self):
        """Test that TOOL_DEFINITIONS is populated (backward compatibility)."""
        assert len(TOOL_DEFINITIONS) > 0
        assert isinstance(TOOL_DEFINITIONS, tuple)

    def test_tool_definitions_by_name_populated(self):
        """Test that TOOL_DEFINITIONS_BY_NAME is populated."""
        assert len(TOOL_DEFINITIONS_BY_NAME) > 0
        assert isinstance(TOOL_DEFINITIONS_BY_NAME, dict)

    def test_specific_tools_present(self):
        """Test that all expected tools are present."""
        tool_names = {td.name for td in TOOL_DEFINITIONS}
        
        # Filesystem tools
        assert 'list_files' in tool_names
        assert 'read_file' in tool_names
        assert 'write_file' in tool_names
        
        # Search tools
        assert 'search_codebase' in tool_names
        assert 'get_project_structure' in tool_names
        
        # Shell tools
        assert 'run_shell_command' in tool_names
        
        # Memory tools
        assert 'save_memory' in tool_names
        assert 'load_memory' in tool_names
        
        # Environment tools
        assert 'manage_environment_vars' in tool_names
        
        # Virtualenv tools
        assert 'create_virtualenv' in tool_names

    def test_all_tools_have_required_fields(self):
        """Test that all tools have required fields."""
        for td in TOOL_DEFINITIONS:
            assert td.name, "Tool must have a name"
            assert td.description, "Tool must have a description"
            assert td.parameters, "Tool must have parameters"
            assert isinstance(td.parameters, dict), "Parameters must be a dict"
            assert td.permission in ["r", "w", "x"], f"Invalid permission: {td.permission}"

    def test_tool_definition_to_openai_schema(self):
        """Test that to_openai_schema method works."""
        for td in TOOL_DEFINITIONS:
            schema = td.to_openai_schema()
            assert isinstance(schema, dict)
            assert "type" in schema
            assert schema["type"] == "function"
            assert "function" in schema
            assert schema["function"]["name"] == td.name