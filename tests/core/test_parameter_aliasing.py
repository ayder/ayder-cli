"""Tests for parameter aliasing functionality."""

import tempfile
import os

from ayder_cli.tools import registry
from ayder_cli.core.context import ProjectContext


def test_parameter_aliases_file_path():
    """Test that 'path' and 'absolute_path' are aliased to 'file_path'."""
    # Create a temp directory as project root for sandboxing
    with tempfile.TemporaryDirectory() as tmp_dir:
        # Set up project context with temp directory as root
        ctx = ProjectContext(tmp_dir)
        
        args = {"path": "test.txt", "start_line": 10}
        normalized = registry.normalize_tool_arguments("read_file", args, ctx)
        assert "file_path" in normalized
        assert os.path.realpath(normalized["file_path"]) == os.path.realpath(os.path.join(tmp_dir, "test.txt"))
        assert "path" not in normalized
        
        args = {"absolute_path": "test.txt"}
        normalized = registry.normalize_tool_arguments("read_file", args, ctx)
        assert "file_path" in normalized
        assert os.path.realpath(normalized["file_path"]) == os.path.realpath(os.path.join(tmp_dir, "test.txt"))
        assert "absolute_path" not in normalized
        
        args = {"filepath": "test.txt"}
        normalized = registry.normalize_tool_arguments("read_file", args, ctx)
        assert "file_path" in normalized
        assert os.path.realpath(normalized["file_path"]) == os.path.realpath(os.path.join(tmp_dir, "test.txt"))
        assert "filepath" not in normalized


def test_parameter_aliases_list_files():
    """Test that 'dir', 'path', 'folder' are aliased to 'directory'."""
    # Create a temp directory as project root for sandboxing
    with tempfile.TemporaryDirectory() as tmp_dir:
        # Set up project context with temp directory as root
        ctx = ProjectContext(tmp_dir)
        
        args = {"dir": "."}
        normalized = registry.normalize_tool_arguments("list_files", args, ctx)
        assert "directory" in normalized
        assert os.path.realpath(normalized["directory"]) == os.path.realpath(tmp_dir)
        assert "dir" not in normalized
        
        args = {"path": "."}
        normalized = registry.normalize_tool_arguments("list_files", args, ctx)
        assert "directory" in normalized
        assert os.path.realpath(normalized["directory"]) == os.path.realpath(tmp_dir)
        
        args = {"folder": "."}
        normalized = registry.normalize_tool_arguments("list_files", args, ctx)
        assert "directory" in normalized
        assert os.path.realpath(normalized["directory"]) == os.path.realpath(tmp_dir)


def test_path_resolution_to_absolute():
    """Test that relative paths are resolved to absolute."""
    # Create a temp directory as project root for sandboxing
    with tempfile.TemporaryDirectory() as tmp_dir:
        # Set up project context with temp directory as root
        ctx = ProjectContext(tmp_dir)
        
        args = {"file_path": "."}
        normalized = registry.normalize_tool_arguments("read_file", args, ctx)
        assert os.path.realpath(normalized["file_path"]) == os.path.realpath(tmp_dir)


def test_type_coercion_line_numbers():
    """Test that string line numbers are coerced to integers."""
    # Create a temp directory as project root for sandboxing
    with tempfile.TemporaryDirectory() as tmp_dir:
        # Set up project context with temp directory as root
        ctx = ProjectContext(tmp_dir)
        
        args = {"file_path": "test.txt", "start_line": "10", "end_line": "20"}
        normalized = registry.normalize_tool_arguments("read_file", args, ctx)
        
        assert isinstance(normalized["start_line"], int)
        assert normalized["start_line"] == 10
        assert isinstance(normalized["end_line"], int)
        assert normalized["end_line"] == 20


def test_validation_wrong_type():
    """Test that validation catches wrong parameter types."""
    # Create a temp directory as project root for sandboxing
    with tempfile.TemporaryDirectory() as tmp_dir:
        # Set up project context with temp directory as root
        ctx = ProjectContext(tmp_dir)
        
        # Test with string where integer expected (and not coercible)
        # Note: normalize_tool_arguments handles coercion for specific fields (start_line, end_line)
        # but validation happens separately.
        # However, normalize_tool_arguments tries to convert line numbers.
        
        args = {"file_path": "test.txt", "start_line": "invalid"}
        
        # Should not raise error during normalization, but conversion might fail or be skipped
        normalized = registry.normalize_tool_arguments("read_file", args, ctx)
        
        # It keeps it as string if conversion fails
        assert normalized["start_line"] == "invalid"
        
        # Now validation should catch it
        is_valid, error = registry.validate_tool_call("read_file", normalized)
        assert not is_valid
        assert "must be an integer" in error


def test_combined_alias_and_normalization():
    """Test combining aliasing with path resolution."""
    # Create a temp directory as project root for sandboxing
    with tempfile.TemporaryDirectory() as tmp_dir:
        # Set up project context with temp directory as root
        ctx = ProjectContext(tmp_dir)
        
        args = {"path": ".", "start_line": "5"}  # Using alias and relative path
        normalized = registry.normalize_tool_arguments("read_file", args, ctx)
        
        assert "file_path" in normalized
        assert os.path.realpath(normalized["file_path"]) == os.path.realpath(tmp_dir)  # Resolved absolute path
        assert normalized["start_line"] == 5  # Coerced to int


def test_backward_compatibility():
    """Test that correct parameter names still work."""
    # Create a temp directory as project root for sandboxing
    with tempfile.TemporaryDirectory() as tmp_dir:
        # Set up project context with temp directory as root
        ctx = ProjectContext(tmp_dir)

        args = {"file_path": "test.txt", "start_line": 10}
        normalized = registry.normalize_tool_arguments("read_file", args, ctx)
        
        assert os.path.realpath(normalized["file_path"]) == os.path.realpath(os.path.join(tmp_dir, "test.txt"))
        assert normalized["start_line"] == 10