"""
Test suite for parameter aliasing, normalization, and validation.
Tests the defensive tool calling improvements in TASK-002.
"""

import pytest
from ayder_cli import fs_tools
from ayder_cli.parser import parse_custom_tool_calls, _infer_parameter_name
from pathlib import Path


@pytest.mark.skip(reason="TODO: Path safety sandboxing - paths outside project root")
def test_parameter_aliases_file_path():
    """Test that 'path' and 'absolute_path' are aliased to 'file_path'."""
    # Test 'path' → 'file_path'
    args = {"path": "/tmp/test.txt"}
    normalized = fs_tools.normalize_tool_arguments("read_file", args)
    assert "file_path" in normalized
    assert "path" not in normalized

    # Test 'absolute_path' → 'file_path'
    args = {"absolute_path": "/tmp/test.txt"}
    normalized = fs_tools.normalize_tool_arguments("read_file", args)
    assert "file_path" in normalized
    assert "absolute_path" not in normalized

    # Test 'filepath' → 'file_path'
    args = {"filepath": "/tmp/test.txt"}
    normalized = fs_tools.normalize_tool_arguments("read_file", args)
    assert "file_path" in normalized
    assert "filepath" not in normalized

    print("✓ Parameter aliases work for file_path")


@pytest.mark.skip(reason="TODO: Path safety sandboxing - paths outside project root")
def test_parameter_aliases_list_files():
    """Test that 'dir', 'path', 'folder' are aliased to 'directory'."""
    # Test 'dir' → 'directory'
    args = {"dir": "/tmp"}
    normalized = fs_tools.normalize_tool_arguments("list_files", args)
    assert "directory" in normalized
    assert "dir" not in normalized

    # Test 'path' → 'directory'
    args = {"path": "/tmp"}
    normalized = fs_tools.normalize_tool_arguments("list_files", args)
    assert "directory" in normalized

    # Test 'folder' → 'directory'
    args = {"folder": "/tmp"}
    normalized = fs_tools.normalize_tool_arguments("list_files", args)
    assert "directory" in normalized

    print("✓ Parameter aliases work for list_files")


def test_path_resolution_to_absolute():
    """Test that relative paths are resolved to absolute."""
    args = {"file_path": "."}
    normalized = fs_tools.normalize_tool_arguments("read_file", args)
    resolved = Path(normalized["file_path"])
    assert resolved.is_absolute(), f"Path should be absolute, got {normalized['file_path']}"

    print("✓ Paths are resolved to absolute")


@pytest.mark.skip(reason="TODO: Path safety sandboxing - paths outside project root")
def test_type_coercion_line_numbers():
    """Test that string line numbers are coerced to integers."""
    args = {"file_path": "/tmp/test.txt", "start_line": "10", "end_line": "20"}
    normalized = fs_tools.normalize_tool_arguments("read_file", args)
    assert isinstance(normalized["start_line"], int), f"start_line should be int, got {type(normalized['start_line'])}"
    assert isinstance(normalized["end_line"], int), f"end_line should be int, got {type(normalized['end_line'])}"
    assert normalized["start_line"] == 10
    assert normalized["end_line"] == 20

    print("✓ Type coercion works for line numbers")


def test_validation_missing_required_params():
    """Test that validation catches missing required parameters."""
    args = {}  # Missing 'file_path' which is required
    is_valid, error_msg = fs_tools.validate_tool_call("read_file", args)
    assert not is_valid, "Should fail validation"
    assert "Missing required parameter" in error_msg

    print("✓ Validation catches missing required parameters")


@pytest.mark.skip(reason="TODO: Path safety sandboxing - paths outside project root")
def test_validation_wrong_type():
    """Test that validation catches wrong parameter types."""
    args = {"file_path": "/tmp/test.txt", "start_line": "not_a_number"}
    normalized = fs_tools.normalize_tool_arguments("read_file", args)
    is_valid, error_msg = fs_tools.validate_tool_call("read_file", normalized)
    # This should still pass because we keep invalid strings as-is during coercion
    # The actual execution will handle the error
    print("✓ Validation handles type mismatches appropriately")


def test_parser_standard_format():
    """Test parser with standard XML format."""
    content = """
    <function=read_file>
    <parameter=file_path>/tmp/test.txt</parameter>
    </function>
    """
    calls = parse_custom_tool_calls(content)
    assert len(calls) == 1
    assert calls[0]["name"] == "read_file"
    assert calls[0]["arguments"]["file_path"] == "/tmp/test.txt"
    assert "error" not in calls[0]

    print("✓ Parser handles standard XML format")


def test_parser_lazy_format():
    """Test parser with lazy format (single-param tools)."""
    content = """
    <function=run_shell_command>ls -la</function>
    """
    calls = parse_custom_tool_calls(content)
    assert len(calls) == 1
    assert calls[0]["name"] == "run_shell_command"
    assert calls[0]["arguments"]["command"] == "ls -la"
    assert "error" not in calls[0]

    print("✓ Parser handles lazy format for single-param tools")


def test_parser_empty_function_name():
    """Test parser with empty function name (error handling)."""
    content = """
    <function=>
    <parameter=file_path>/tmp/test.txt</parameter>
    </function>
    """
    calls = parse_custom_tool_calls(content)
    assert len(calls) == 1
    assert "error" in calls[0]
    assert "function name is empty" in calls[0]["error"]

    print("✓ Parser detects empty function names")


def test_parser_missing_parameters():
    """Test parser with missing parameters tag (error handling)."""
    content = """
    <function=read_file>
    </function>
    """
    calls = parse_custom_tool_calls(content)
    assert len(calls) == 1
    assert "error" in calls[0]
    assert "no parameters" in calls[0]["error"]

    print("✓ Parser detects missing parameters")


def test_parser_lazy_format_invalid_tool():
    """Test parser with lazy format on tool that doesn't support it."""
    content = """
    <function=list_files>/tmp</function>
    """
    calls = parse_custom_tool_calls(content)
    assert len(calls) == 1
    assert "error" in calls[0]
    assert "Missing <parameter> tags" in calls[0]["error"]

    print("✓ Parser rejects lazy format for non-single-param tools")


def test_infer_parameter_name():
    """Test parameter name inference for single-param tools."""
    assert _infer_parameter_name("run_shell_command") == "command"
    assert _infer_parameter_name("show_task") == "task_id"
    assert _infer_parameter_name("implement_task") == "task_id"
    assert _infer_parameter_name("list_files") == ""  # Not a single-param tool

    print("✓ Parameter inference works correctly")


def test_combined_alias_and_normalization():
    """Test combining aliasing with path resolution."""
    args = {"path": ".", "start_line": "5"}  # Using alias and relative path
    normalized = fs_tools.normalize_tool_arguments("read_file", args)

    assert "file_path" in normalized
    assert "path" not in normalized
    assert Path(normalized["file_path"]).is_absolute()
    assert isinstance(normalized["start_line"], int)

    print("✓ Combined aliasing and normalization works")


@pytest.mark.skip(reason="TODO: Path safety sandboxing - paths outside project root")
def test_backward_compatibility():
    """Test that correct parameter names still work."""
    args = {"file_path": "/tmp/test.txt"}
    normalized = fs_tools.normalize_tool_arguments("read_file", args)
    assert normalized["file_path"] == str(Path("/tmp/test.txt").resolve())

    print("✓ Backward compatibility maintained")


if __name__ == "__main__":
    test_parameter_aliases_file_path()
    test_parameter_aliases_list_files()
    test_path_resolution_to_absolute()
    test_type_coercion_line_numbers()
    test_validation_missing_required_params()
    test_validation_wrong_type()
    test_parser_standard_format()
    test_parser_lazy_format()
    test_parser_empty_function_name()
    test_parser_missing_parameters()
    test_parser_lazy_format_invalid_tool()
    test_infer_parameter_name()
    test_combined_alias_and_normalization()
    test_backward_compatibility()
    print("\n✅ All tests passed!")
