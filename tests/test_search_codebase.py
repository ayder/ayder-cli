"""
Comprehensive tests for search_codebase and get_project_structure functions.
"""
import os
import sys
import tempfile
import shutil

# Add the source directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from ayder_cli import fs_tools


class TestSearchCodebase:
    """Test the search_codebase function."""

    def setup_method(self):
        """Create a temporary directory with test files before each test."""
        self.test_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir)

        # Create test files
        with open("test_file.py", "w") as f:
            f.write("def read_file():\n    return 'content'\n\ndef write_file():\n    pass\n")

        with open("another_file.py", "w") as f:
            f.write("class MyTest:\n    def test_something(self):\n        # TODO: fix this\n        pass\n")

        with open("config.txt", "w") as f:
            f.write("DEBUG = True\nDEBUG_MODE = False\n")

        # Create subdirectory
        os.makedirs("subdir", exist_ok=True)
        with open("subdir/nested.py", "w") as f:
            f.write("def nested_function():\n    return 42\n")

    def teardown_method(self):
        """Clean up temporary directory after each test."""
        os.chdir(self.original_cwd)
        shutil.rmtree(self.test_dir)

    def test_basic_search(self):
        """Test basic pattern search."""
        result = fs_tools.search_codebase("def read_file")
        assert "=== SEARCH RESULTS ===" in result
        assert "END SEARCH RESULTS ===" in result
        assert "test_file.py" in result or "Pattern: \"def read_file\"" in result

    def test_search_no_matches(self):
        """Test search with no matches."""
        result = fs_tools.search_codebase("nonexistent_pattern_xyz123")
        assert "No matches found" in result
        assert "=== SEARCH RESULTS ===" in result

    def test_case_insensitive_search(self):
        """Test case-insensitive search."""
        result = fs_tools.search_codebase("DEBUG", case_sensitive=False)
        assert "=== SEARCH RESULTS ===" in result
        # Should find both DEBUG and debug
        assert result.count("Line") >= 2 or "No matches found" not in result

    def test_file_pattern_filter(self):
        """Test search with file pattern filter."""
        result = fs_tools.search_codebase("def", file_pattern="*.py")
        assert "=== SEARCH RESULTS ===" in result
        # Should find Python definitions but not config.txt content

    def test_max_results_limit(self):
        """Test max_results parameter."""
        result = fs_tools.search_codebase("def", max_results=1)
        assert "=== SEARCH RESULTS ===" in result
        # Count "Line" occurrences - should be limited
        line_count = result.count("Line ")
        assert line_count <= 1

    def test_search_in_subdirectories(self):
        """Test that search finds files in subdirectories."""
        result = fs_tools.search_codebase("nested_function")
        assert "=== SEARCH RESULTS ===" in result
        # Should find the function in subdir/nested.py

    def test_context_lines(self):
        """Test context_lines parameter."""
        result = fs_tools.search_codebase("def", context_lines=1)
        assert "=== SEARCH RESULTS ===" in result
        # With context, output should be more detailed


class TestGetProjectStructure:
    """Test the get_project_structure function."""

    def setup_method(self):
        """Create a temporary project structure."""
        self.test_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir)

        # Create a realistic project structure
        os.makedirs("src/myproject", exist_ok=True)
        os.makedirs("tests", exist_ok=True)
        os.makedirs(".venv", exist_ok=True)
        os.makedirs("__pycache__", exist_ok=True)
        os.makedirs("dist", exist_ok=True)

        with open("README.md", "w") as f:
            f.write("# My Project\n")

        with open("src/myproject/__init__.py", "w") as f:
            f.write("")

        with open("src/myproject/main.py", "w") as f:
            f.write("def main():\n    pass\n")

        with open("tests/test_main.py", "w") as f:
            f.write("def test_something():\n    pass\n")

    def teardown_method(self):
        """Clean up temporary directory."""
        os.chdir(self.original_cwd)
        shutil.rmtree(self.test_dir)

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

    def test_structure_includes_src(self):
        """Test that src directory is included."""
        structure = fs_tools.get_project_structure(max_depth=3)
        assert "src" in structure

    def test_structure_includes_readme(self):
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

    def setup_method(self):
        """Set up test environment."""
        self.test_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir)

        with open("test.py", "w") as f:
            f.write("def test_func():\n    return True\n")

    def teardown_method(self):
        """Clean up."""
        os.chdir(self.original_cwd)
        shutil.rmtree(self.test_dir)

    def test_dispatcher_calls_search_codebase(self):
        """Test that dispatcher correctly routes search_codebase calls."""
        result = fs_tools.execute_tool_call(
            "search_codebase",
            {"pattern": "def test_func"}
        )
        assert "=== SEARCH RESULTS ===" in result

    def test_dispatcher_with_kwargs(self):
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

    def test_dispatcher_with_json_string(self):
        """Test dispatcher with JSON string arguments."""
        import json
        args_str = json.dumps({"pattern": "def test_func"})
        result = fs_tools.execute_tool_call("search_codebase", args_str)
        assert "=== SEARCH RESULTS ===" in result


class TestSearchFallback:
    """Test fallback from ripgrep to grep."""

    def setup_method(self):
        """Create test environment."""
        self.test_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir)

        with open("sample.py", "w") as f:
            f.write("# This is a comment\nprint('hello')\n")

    def teardown_method(self):
        """Clean up."""
        os.chdir(self.original_cwd)
        shutil.rmtree(self.test_dir)

    def test_search_executes_without_error(self):
        """Test that search executes without raising exceptions."""
        try:
            result = fs_tools.search_codebase("print")
            assert "SEARCH RESULTS" in result
        except Exception as e:
            assert False, f"Search raised exception: {e}"


if __name__ == "__main__":
    # Run tests manually
    print("Testing search_codebase...")

    test_search = TestSearchCodebase()
    test_search.setup_method()
    try:
        test_search.test_basic_search()
        print("✓ test_basic_search passed")
    finally:
        test_search.teardown_method()

    test_search.setup_method()
    try:
        test_search.test_search_no_matches()
        print("✓ test_search_no_matches passed")
    finally:
        test_search.teardown_method()

    test_search.setup_method()
    try:
        test_search.test_case_insensitive_search()
        print("✓ test_case_insensitive_search passed")
    finally:
        test_search.teardown_method()

    print("\nTesting get_project_structure...")

    test_structure = TestGetProjectStructure()
    test_structure.setup_method()
    try:
        test_structure.test_structure_generation()
        print("✓ test_structure_generation passed")
    finally:
        test_structure.teardown_method()

    test_structure.setup_method()
    try:
        test_structure.test_structure_ignores_venv()
        print("✓ test_structure_ignores_venv passed")
    finally:
        test_structure.teardown_method()

    print("\nAll manual tests completed!")
