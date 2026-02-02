"""Tests for path safety and sandboxing."""

import pytest
from pathlib import Path
from ayder_cli.path_context import ProjectContext


class TestProjectContext:
    """Test ProjectContext class."""
    
    def test_init_expands_tilde(self, tmp_path, monkeypatch):
        """Test that ~ is expanded correctly."""
        # Mock expanduser to return tmp_path
        import os
        monkeypatch.setenv('HOME', str(tmp_path))
        
        ctx = ProjectContext("~")
        assert str(ctx.root) == str(tmp_path.resolve())
    
    def test_validate_path_relative(self, tmp_path):
        """Test validating relative paths."""
        ctx = ProjectContext(str(tmp_path))
        
        # Create a file
        (tmp_path / "test.txt").write_text("content")
        
        abs_path = ctx.validate_path("test.txt")
        assert abs_path == tmp_path / "test.txt"
    
    def test_validate_path_absolute_within_root(self, tmp_path):
        """Test validating absolute paths within root."""
        ctx = ProjectContext(str(tmp_path))
        
        (tmp_path / "subdir").mkdir()
        (tmp_path / "subdir" / "file.txt").write_text("content")
        
        abs_path = ctx.validate_path(str(tmp_path / "subdir" / "file.txt"))
        assert abs_path == tmp_path / "subdir" / "file.txt"
    
    def test_validate_path_rejects_outside_root(self, tmp_path):
        """Test that paths outside root are rejected."""
        ctx = ProjectContext(str(tmp_path))
        
        with pytest.raises(ValueError, match="Security Alert"):
            ctx.validate_path("../outside.txt")
        
        with pytest.raises(ValueError, match="Security Alert"):
            ctx.validate_path("/etc/passwd")
    
    def test_to_relative(self, tmp_path):
        """Test converting absolute to relative path."""
        ctx = ProjectContext(str(tmp_path))
        
        abs_path = tmp_path / "src" / "main.py"
        rel = ctx.to_relative(abs_path)
        assert rel == "src/main.py"
    
    def test_to_relative_fallback_outside_root(self, tmp_path):
        """Test fallback for paths outside root."""
        ctx = ProjectContext(str(tmp_path))
        
        outside_path = Path("/some/other/path")
        result = ctx.to_relative(outside_path)
        assert result == str(outside_path)


class TestToolPathSecurity:
    """Test that tools enforce path security."""
    
    def test_read_file_rejects_path_traversal(self, tmp_path, monkeypatch):
        """Test read_file rejects ../ paths."""
        from ayder_cli.tools import impl
        
        ctx = ProjectContext(str(tmp_path))
        monkeypatch.setattr(impl, "_default_project_ctx", ctx)
        
        result = impl.read_file("../etc/passwd")
        assert "Security Error" in result
    
    def test_write_file_rejects_path_traversal(self, tmp_path, monkeypatch):
        """Test write_file rejects ../ paths."""
        from ayder_cli.tools import impl
        
        ctx = ProjectContext(str(tmp_path))
        monkeypatch.setattr(impl, "_default_project_ctx", ctx)
        
        result = impl.write_file("../outside.txt", "content")
        assert "Security Error" in result
    
    def test_list_files_rejects_path_traversal(self, tmp_path, monkeypatch):
        """Test list_files rejects ../ paths."""
        from ayder_cli.tools import impl
        
        ctx = ProjectContext(str(tmp_path))
        monkeypatch.setattr(impl, "_default_project_ctx", ctx)
        
        result = impl.list_files("../")
        assert "Security Error" in result
    
    def test_replace_string_rejects_path_traversal(self, tmp_path, monkeypatch):
        """Test replace_string rejects ../ paths."""
        from ayder_cli.tools import impl
        
        ctx = ProjectContext(str(tmp_path))
        monkeypatch.setattr(impl, "_default_project_ctx", ctx)
        
        result = impl.replace_string("../outside.txt", "old", "new")
        assert "Security Error" in result
    
    def test_search_codebase_rejects_path_traversal(self, tmp_path, monkeypatch):
        """Test search_codebase rejects ../ paths."""
        from ayder_cli.tools import impl
        
        ctx = ProjectContext(str(tmp_path))
        monkeypatch.setattr(impl, "_default_project_ctx", ctx)
        
        result = impl.search_codebase("pattern", directory="../")
        assert "Security Error" in result


class TestPathTraversalVariations:
    """Test various path traversal attack patterns."""
    
    def test_double_dot_traversal(self, tmp_path):
        """Test basic ../ traversal."""
        ctx = ProjectContext(str(tmp_path))
        
        with pytest.raises(ValueError, match="Security Alert"):
            ctx.validate_path("../secret.txt")
    
    def test_multiple_double_dots(self, tmp_path):
        """Test multiple ../ sequences."""
        ctx = ProjectContext(str(tmp_path))
        
        with pytest.raises(ValueError, match="Security Alert"):
            ctx.validate_path("../../etc/passwd")
    
    def test_mixed_traversal(self, tmp_path):
        """Test mixed valid and invalid paths."""
        ctx = ProjectContext(str(tmp_path))
        
        # Valid path
        (tmp_path / "subdir").mkdir()
        valid_path = ctx.validate_path("subdir/../file.txt")
        # Path is resolved, so it should be valid
        assert valid_path == tmp_path / "file.txt"
    
    def test_absolute_outside_root(self, tmp_path):
        """Test absolute path outside root."""
        ctx = ProjectContext(str(tmp_path))
        
        with pytest.raises(ValueError, match="Security Alert"):
            ctx.validate_path("/etc/passwd")
    
    def test_tilde_expansion(self, tmp_path, monkeypatch):
        """Test that ~ is expanded and validated."""
        import os
        monkeypatch.setenv('HOME', str(tmp_path))
        
        ctx = ProjectContext(str(tmp_path))
        
        # Create file in tmp_path (which is mocked as HOME)
        (tmp_path / "file.txt").write_text("content")
        
        # Should work because ~ expands to tmp_path which is the root
        abs_path = ctx.validate_path("~/file.txt")
        assert abs_path == tmp_path / "file.txt"
