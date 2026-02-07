"""Tests for path security enforcement."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from ayder_cli.tools import impl
from ayder_cli.core.context import ProjectContext
from ayder_cli.core.result import ToolError


class TestToolPathSecurity:
    """Test that tools reject paths outside the project root."""

    def test_validate_path_security(self, tmp_path):
        """Test basic path validation."""
        ctx = ProjectContext(str(tmp_path))
    
        # Should pass
        assert ctx.validate_path("file.txt") == tmp_path / "file.txt"
    
        # Should pass (subdirectory)
        assert ctx.validate_path("subdir/file.txt") == tmp_path / "subdir" / "file.txt"
    
        # Should fail (parent directory)
        with pytest.raises(ValueError, match="Security Alert"):
            ctx.validate_path("../outside.txt")
            
        # Should fail (absolute path outside)
        with pytest.raises(ValueError, match="Security Alert"):
            ctx.validate_path("/etc/passwd")

    def test_tools_use_path_validation(self, tmp_path):
        """Test that tools use the validation logic."""
        ctx = ProjectContext(str(tmp_path))

        # Mock validate_path to ensure it's called
        with patch.object(ProjectContext, 'validate_path', side_effect=ValueError("Access denied")) as mock_validate:
            # list_files
            result = impl.list_files(ctx, ".")
            assert isinstance(result, ToolError)
            assert result.category == "security"
            assert "Security Error" in result
            mock_validate.assert_called()

            # read_file
            result = impl.read_file(ctx, "file.txt")
            assert isinstance(result, ToolError)
            assert result.category == "security"
            assert "Security Error" in result

            # write_file
            result = impl.write_file(ctx, "file.txt", "content")
            assert isinstance(result, ToolError)
            assert result.category == "security"
            assert "Security Error" in result

    def test_read_file_rejects_path_traversal(self, tmp_path):
        """Test read_file rejects ../ paths."""
        ctx = ProjectContext(str(tmp_path))
        
        # Create file outside root
        outside_file = tmp_path.parent / "outside.txt"
        try:
            outside_file.write_text("secret")
            
            # Try to read it
            result = impl.read_file(ctx, "../outside.txt")
            assert isinstance(result, ToolError)
            assert result.category == "security"
            assert "Security Error" in result
            assert "Security Alert" in result
        except PermissionError:
            pass  # Can't write to parent dir in some envs

    def test_write_file_rejects_path_traversal(self, tmp_path):
        """Test write_file rejects ../ paths."""
        ctx = ProjectContext(str(tmp_path))

        result = impl.write_file(ctx, "../outside.txt", "content")
        assert isinstance(result, ToolError)
        assert result.category == "security"
        assert "Security Error" in result
        assert "Security Alert" in result

    def test_list_files_rejects_path_traversal(self, tmp_path):
        """Test list_files rejects ../ paths."""
        ctx = ProjectContext(str(tmp_path))

        result = impl.list_files(ctx, "..")
        assert isinstance(result, ToolError)
        assert result.category == "security"
        assert "Security Error" in result
        assert "Security Alert" in result

    def test_replace_string_rejects_path_traversal(self, tmp_path):
        """Test replace_string rejects ../ paths."""
        ctx = ProjectContext(str(tmp_path))

        result = impl.replace_string(ctx, "../outside.txt", "old", "new")
        assert isinstance(result, ToolError)
        assert result.category == "security"
        assert "Security Error" in result
        assert "Security Alert" in result

    def test_search_codebase_rejects_path_traversal(self, tmp_path):
        """Test search_codebase rejects ../ paths."""
        ctx = ProjectContext(str(tmp_path))

        result = impl.search_codebase(ctx, "pattern", directory="..")
        assert isinstance(result, ToolError)
        assert result.category == "security"
        assert "Security Error" in result
        assert "Security Alert" in result