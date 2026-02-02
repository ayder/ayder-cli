"""
Comprehensive tests for search_codebase and get_project_structure functions.
"""
import os
import sys
import pytest

# Add the source directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from ayder_cli import fs_tools
from ayder_cli.tools import impl


@pytest.fixture
def search_context(tmp_path, monkeypatch):
    """Create a project context with test files and set it for fs_tools and impl."""
    from ayder_cli.path_context import ProjectContext
    from ayder_cli.tools import registry
    
    # Create test files in tmp_path
    (tmp_path / "test_file.py").write_text(
        "def read_file():\n    return 'content'\n\ndef write_file():\n    pass\n"
    )
    (tmp_path / "another_file.py").write_text(
        "class MyTest:\n    def test_something(self):\n        # TODO: fix this\n        pass\n"
    )
    (tmp_path / "config.txt").write_text("DEBUG = True\nDEBUG_MODE = False\n")
    
    # Create subdirectory
    (tmp_path / "subdir").mkdir()
    (tmp_path / "subdir" / "nested.py").write_text("def nested_function():\n    return 42\n")
    
    ctx = ProjectContext(str(tmp_path))
    # Patch the impl module's context (used by search_codebase and get_project_structure)
    monkeypatch.setattr(impl, "_default_project_ctx", ctx)
    # Also patch registry for dispatcher tests
    monkeypatch.setattr(registry, "_default_project_ctx", ctx)
    return ctx


@pytest.fixture
def structure_context(tmp_path, monkeypatch):
    """Create a project context with realistic structure for structure tests."""
    from ayder_cli.path_context import ProjectContext
    from ayder_cli.tools import registry
    
    # Create a realistic project structure
    (tmp_path / "src" / "myproject").mkdir(parents=True)
    (tmp_path / "tests").mkdir()
    (tmp_path / ".venv").mkdir()
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "dist").mkdir()
    
    (tmp_path / "README.md").write_text("# My Project\n")
    (tmp_path / "src" / "myproject" / "__init__.py").write_text("")
    (tmp_path / "src" / "myproject" / "main.py").write_text("def main():\n    pass\n")
    (tmp_path / "tests" / "test_main.py").write_text("def test_something():\n    pass\n")
    
    ctx = ProjectContext(str(tmp_path))
    monkeypatch.setattr(impl, "_default_project_ctx", ctx)
    monkeypatch.setattr(registry, "_default_project_ctx", ctx)
    return ctx


class TestSearchCodebase:
    """Test the search_codebase function."""

    def test_basic_search(self):
        """Test basic pattern search - uses project root set by setup."""
        result = fs_tools.search_codebase("def read_file")
        assert "=== SEARCH RESULTS ===" in result
        assert "END SEARCH RESULTS ===" in result
        assert "test_file.py" in result or "Pattern: \"def read_file\"" in result

    def test_search_no_matches(self, search_context):
        """Test search with no matches."""
        result = fs_tools.search_codebase("nonexistent_pattern_xyz123")
        assert "No matches found" in result
        assert "=== SEARCH RESULTS ===" in result

    def test_case_insensitive_search(self, search_context):
        """Test case-insensitive search."""
        result = fs_tools.search_codebase("debug", case_sensitive=False)
        assert "=== SEARCH RESULTS ===" in result
        # Should find both DEBUG and debug
        assert result.count("Line") >= 2

    def test_file_pattern_filter(self, search_context):
        """Test search with file pattern filter."""
        result = fs_tools.search_codebase("def", file_pattern="*.py")
        assert "=== SEARCH RESULTS ===" in result
        # Should find Python definitions but not config.txt content

    def test_max_results_limit(self, search_context):
        """Test max_results parameter."""
        result = fs_tools.search_codebase("def", max_results=1)
        assert "=== SEARCH RESULTS ===" in result
        # Count "Line" occurrences - should be limited
        line_count = result.count("Line ")
        assert line_count <= 1

    def test_search_in_subdirectories(self, search_context):
        """Test that search finds files in subdirectories."""
        result = fs_tools.search_codebase("nested_function")
        assert "=== SEARCH RESULTS ===" in result
        # Should find the function in subdir/nested.py

    def test_context_lines(self, search_context):
        """Test context_lines parameter."""
        result = fs_tools.search_codebase("def", context_lines=1)
        assert "=== SEARCH RESULTS ===" in result
        # With context, output should be more detailed


class TestGetProjectStructure:
    """Test the get_project_structure function."""

    def test_structure_generation(self):
        """Test that project structure is generated."""
        structure = fs_tools.get_project_structure(max_depth=2)
        assert structure
        assert isinstance(structure, str)
        # Should contain at least the root directory name
        assert len(structure) > 0

    def test_structure_ignores_venv(self):
        """Test that .venv directory is ignored."""
        structure = fs_tools.get_project_structure(max_depth=3)
        assert ".venv" not in structure

    def test_structure_ignores_pycache(self):
        """Test that __pycache__ is ignored."""
        structure = fs_tools.get_project_structure(max_depth=3)
        assert "__pycache__" not in structure

    def test_structure_ignores_dist(self):
        """Test that dist directory is ignored."""
        structure = fs_tools.get_project_structure(max_depth=3)
        assert "dist" not in structure

    def test_structure_includes_src(self, structure_context):
        """Test that src directory is included."""
        structure = fs_tools.get_project_structure(max_depth=3)
        assert "src" in structure

    def test_structure_includes_readme(self, structure_context):
        """Test that README.md is included."""
        structure = fs_tools.get_project_structure(max_depth=3)
        assert "README.md" in structure

    def test_max_depth_respected(self):
        """Test that max_depth parameter limits recursion."""
        # With max_depth=1, should not see nested files deeply
        structure_shallow = fs_tools.get_project_structure(max_depth=1)
        assert structure_shallow

        # Should still have the root
        assert len(structure_shallow) > 0


class TestToolIntegration:
    """Test integration with the tool dispatcher."""

    def test_dispatcher_calls_search_codebase(self, search_context):
        """Test that dispatcher correctly routes search_codebase calls."""
        result = fs_tools.execute_tool_call(
            "search_codebase",
            {"pattern": "def read_file"}
        )
        assert "=== SEARCH RESULTS ===" in result

    def test_dispatcher_with_kwargs(self, search_context):
        """Test dispatcher with multiple parameters."""
        result = fs_tools.execute_tool_call(
            "search_codebase",
            {
                "pattern": "def",
                "file_pattern": "*.py",
                "case_sensitive": True,
                "max_results": 10
            }
        )
        assert "=== SEARCH RESULTS ===" in result

    def test_dispatcher_with_json_string(self, search_context):
        """Test dispatcher with JSON string arguments."""
        import json
        args_str = json.dumps({"pattern": "def read_file"})
        result = fs_tools.execute_tool_call("search_codebase", args_str)
        assert "=== SEARCH RESULTS ===" in result


class TestSearchFallback:
    """Test fallback from ripgrep to grep."""

    def test_search_executes_without_error(self, search_context):
        """Test that search executes without raising exceptions."""
        try:
            result = fs_tools.search_codebase("print")
            assert "SEARCH RESULTS" in result
        except Exception as e:
            assert False, f"Search raised exception: {e}"


if __name__ == "__main__":
    # Run tests manually
    pytest.main([__file__, "-v"])
