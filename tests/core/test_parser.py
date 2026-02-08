"""Tests for parser.py module.

This module tests the parser functionality including:
- Line 13: Empty content check returns []
- Standard format parsing
- Lazy format parsing
- Error handling
"""

import pytest

from ayder_cli.parser import parse_custom_tool_calls, _infer_parameter_name


class TestParseCustomToolCallsEmpty:
    """Tests for empty content handling - Line 13."""

    def test_empty_string_returns_empty_list(self):
        """Test that empty string returns empty list."""
        result = parse_custom_tool_calls("")
        assert result == []

    def test_none_returns_empty_list(self):
        """Test that None returns empty list."""
        result = parse_custom_tool_calls(None)
        assert result == []

    def test_whitespace_only_returns_empty_list(self):
        """Test that whitespace-only string returns empty list."""
        result = parse_custom_tool_calls("   \n\t  ")
        assert result == []


class TestParseCustomToolCallsStandardFormat:
    """Tests for standard format parsing with parameter tags."""

    def test_single_parameter(self):
        """Test parsing with single parameter."""
        content = '<function=write_file><parameter=file_path>/tmp/test.txt</parameter></function>'
        result = parse_custom_tool_calls(content)
        
        assert len(result) == 1
        assert result[0]["name"] == "write_file"
        assert result[0]["arguments"] == {"file_path": "/tmp/test.txt"}

    def test_multiple_parameters(self):
        """Test parsing with multiple parameters."""
        content = '<function=replace_string><parameter=file_path>/tmp/test.txt</parameter><parameter=old_string>old</parameter><parameter=new_string>new</parameter></function>'
        result = parse_custom_tool_calls(content)
        
        assert len(result) == 1
        assert result[0]["name"] == "replace_string"
        assert result[0]["arguments"] == {
            "file_path": "/tmp/test.txt",
            "old_string": "old",
            "new_string": "new"
        }

    def test_multiple_function_calls(self):
        """Test parsing multiple function calls in one content."""
        content = (
            '<function=read_file><parameter=file_path>/file1.txt</parameter></function>'
            '<function=read_file><parameter=file_path>/file2.txt</parameter></function>'
        )
        result = parse_custom_tool_calls(content)
        
        assert len(result) == 2
        assert result[0]["arguments"]["file_path"] == "/file1.txt"
        assert result[1]["arguments"]["file_path"] == "/file2.txt"

    def test_multiline_parameter_value(self):
        """Test parsing with multiline parameter value."""
        content = '<function=write_file><parameter=content>Line 1\nLine 2\nLine 3</parameter></function>'
        result = parse_custom_tool_calls(content)
        
        assert result[0]["arguments"]["content"] == "Line 1\nLine 2\nLine 3"


class TestParseCustomToolCallsLazyFormat:
    """Tests for lazy format parsing (single parameter without tags)."""

    def test_run_shell_command_lazy(self):
        """Test lazy parsing for run_shell_command."""
        content = '<function=run_shell_command>ls -la</function>'
        result = parse_custom_tool_calls(content)
        
        assert len(result) == 1
        assert result[0]["name"] == "run_shell_command"
        assert result[0]["arguments"] == {"command": "ls -la"}

    def test_unknown_tool_lazy_no_infer(self):
        """Test lazy parsing for unknown tool without parameter inference."""
        content = '<function=unknown_tool>some value</function>'
        result = parse_custom_tool_calls(content)
        
        assert result[0]["name"] == "unknown_tool"
        assert "error" in result[0]
        assert "Missing <parameter> tags" in result[0]["error"]


class TestParseCustomToolCallsErrorHandling:
    """Tests for error handling in parsing."""

    def test_empty_function_name(self):
        """Test handling of empty function name."""
        content = '<function= ><parameter=key>value</parameter></function>'
        result = parse_custom_tool_calls(content)
        
        assert len(result) == 1
        assert result[0]["name"] == "unknown"
        assert "error" in result[0]
        assert "function name is empty" in result[0]["error"]

    def test_no_parameters(self):
        """Test handling of function call with no parameters."""
        content = '<function=read_file></function>'
        result = parse_custom_tool_calls(content)
        
        assert len(result) == 1
        assert result[0]["name"] == "read_file"
        assert "error" in result[0]
        assert "no parameters" in result[0]["error"]

    def test_empty_body(self):
        """Test handling of function call with empty body."""
        content = '<function=read_file>   </function>'
        result = parse_custom_tool_calls(content)
        
        assert len(result) == 1
        assert "error" in result[0]

    def test_empty_parameter_name(self):
        """Test handling of empty parameter name."""
        content = '<function=read_file><parameter=>value</parameter></function>'
        result = parse_custom_tool_calls(content)
        
        # Empty parameter names should be ignored
        assert result[0]["arguments"] == {}


class TestInferParameterName:
    """Tests for _infer_parameter_name() function."""

    def test_run_shell_command(self):
        """Test inference for run_shell_command."""
        assert _infer_parameter_name("run_shell_command") == "command"

    def test_unknown_tool(self):
        """Test inference for unknown tool returns empty string."""
        assert _infer_parameter_name("unknown_tool") == ""

    def test_empty_string(self):
        """Test inference for empty string returns empty string."""
        assert _infer_parameter_name("") == ""
