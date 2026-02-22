"""Tests for codebase search functionality."""

import pytest
from unittest.mock import patch, MagicMock

from ayder_cli.tools.builtins import search, utils_tools
from ayder_cli.core.context import ProjectContext
from ayder_cli.core.result import ToolSuccess

# Create a namespace object that mimicks the old 'impl' module
class ImplNamespace:
    pass

impl = ImplNamespace()
impl.search_codebase = search.search_codebase
impl.get_project_structure = utils_tools.get_project_structure


@pytest.fixture
def search_context(tmp_path):
    """Create a project context with test files."""
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

    return ProjectContext(str(tmp_path))


class TestSearchCodebase:
    """Test search_codebase functionality."""

    @patch("ayder_cli.tools.builtins.search.shutil.which")
    @patch("ayder_cli.tools.builtins.search.subprocess.run")
    def test_basic_search(self, mock_run, mock_which, search_context):
        """Test basic pattern search."""
        mock_which.return_value = "/usr/bin/rg"
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="test_file.py\n1:def read_file():\n",
            stderr=""
        )

        result = impl.search_codebase(search_context, "def read_file")

        assert isinstance(result, ToolSuccess)
        assert "Matches found" in result
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "def read_file" in cmd

    @patch("ayder_cli.tools.builtins.search.shutil.which")
    @patch("ayder_cli.tools.builtins.search.subprocess.run")
    def test_search_no_matches(self, mock_run, mock_which, search_context):
        """Test search with no matches."""
        mock_which.return_value = "/usr/bin/rg"
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")

        result = impl.search_codebase(search_context, "nonexistent_pattern")

        assert isinstance(result, ToolSuccess)
        assert "No matches found" in result

    @patch("ayder_cli.tools.builtins.search.shutil.which")
    @patch("ayder_cli.tools.builtins.search.subprocess.run")
    def test_case_insensitive_search(self, mock_run, mock_which, search_context):
        """Test case-insensitive search."""
        mock_which.return_value = "/usr/bin/rg"
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        impl.search_codebase(search_context, "READ_FILE", case_sensitive=False)
        
        cmd = mock_run.call_args[0][0]
        assert "--ignore-case" in cmd

    @patch("ayder_cli.tools.builtins.search.shutil.which")
    @patch("ayder_cli.tools.builtins.search.subprocess.run")
    def test_file_pattern_filter(self, mock_run, mock_which, search_context):
        """Test search filtered by file pattern."""
        mock_which.return_value = "/usr/bin/rg"
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        impl.search_codebase(search_context, "def", file_pattern="*.py")
        
        cmd = mock_run.call_args[0][0]
        assert "--glob" in cmd
        assert "*.py" in cmd

    @patch("ayder_cli.tools.builtins.search.shutil.which")
    @patch("ayder_cli.tools.builtins.search.subprocess.run")
    def test_max_results_limit(self, mock_run, mock_which, search_context):
        """Test max results limit."""
        mock_which.return_value = "/usr/bin/rg"
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        impl.search_codebase(search_context, "def", max_results=10)
        
        cmd = mock_run.call_args[0][0]
        assert "--max-count" in cmd
        assert "10" in cmd

    @patch("ayder_cli.tools.builtins.search.shutil.which")
    @patch("ayder_cli.tools.builtins.search.subprocess.run")
    def test_search_in_subdirectories(self, mock_run, mock_which, search_context):
        """Test search in subdirectories."""
        mock_which.return_value = "/usr/bin/rg"
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        impl.search_codebase(search_context, "def", directory="subdir")
        
        cmd = mock_run.call_args[0][0]
        # Should contain the absolute path to subdir
        assert str(search_context.root / "subdir") in cmd

    @patch("ayder_cli.tools.builtins.search.shutil.which")
    @patch("ayder_cli.tools.builtins.search.subprocess.run")
    def test_context_lines(self, mock_run, mock_which, search_context):
        """Test searching with context lines."""
        mock_which.return_value = "/usr/bin/rg"
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        impl.search_codebase(search_context, "def", context_lines=3)
        
        cmd = mock_run.call_args[0][0]
        assert "--context" in cmd
        assert "3" in cmd


@pytest.fixture
def structure_context(tmp_path):
    """Create a project context with realistic structure for structure tests."""
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

    return ProjectContext(str(tmp_path))


class TestGetProjectStructure:
    """Test get_project_structure functionality."""

    def test_structure_generation(self, structure_context):
        """Test that project structure is generated."""
        structure = impl.get_project_structure(structure_context, max_depth=2)
        assert "README.md" in structure
        assert "src" in structure
        assert "tests" in structure

    def test_structure_ignores_venv(self, structure_context):
        """Test that .venv directory is ignored."""
        structure = impl.get_project_structure(structure_context, max_depth=3)
        assert ".venv" not in structure

    def test_structure_ignores_pycache(self, structure_context):
        """Test that __pycache__ is ignored."""
        structure = impl.get_project_structure(structure_context, max_depth=3)
        assert "__pycache__" not in structure

    def test_structure_ignores_dist(self, structure_context):
        """Test that dist directory is ignored."""
        structure = impl.get_project_structure(structure_context, max_depth=3)
        assert "dist" not in structure

    def test_structure_includes_src(self, structure_context):
        """Test that src files are included."""
        structure = impl.get_project_structure(structure_context, max_depth=3)
        assert "src/myproject/main.py" in structure or "main.py" in structure

    def test_structure_includes_readme(self, structure_context):
        """Test that README is included."""
        structure = impl.get_project_structure(structure_context, max_depth=1)
        assert "README.md" in structure

    def test_max_depth_respected(self, structure_context):
        """Test that max_depth parameter limits recursion."""
        # With max_depth=1, should not see nested files deeply
        structure_shallow = impl.get_project_structure(structure_context, max_depth=1)
        # Should see top level dirs but maybe not contents
        assert "src" in structure_shallow
        
        # Checking logic might depend on how manual tree is implemented
        # manual tree shows files at current level + folders, recurses if depth < max
        # If max_depth=1, only root items.
        
        # Verify deeper items are present with more depth
        structure_deep = impl.get_project_structure(structure_context, max_depth=5)
        assert len(structure_deep) > len(structure_shallow)


class TestToolIntegration:
    """Test integration between dispatcher and search tools."""

    @patch("ayder_cli.tools.builtins.search.shutil.which")
    @patch("ayder_cli.tools.builtins.search.subprocess.run")
    def test_dispatcher_calls_search_codebase(self, mock_run, mock_which, search_context):
        """Test that dispatcher correctly calls search_codebase."""
        mock_which.return_value = "/usr/bin/rg"
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        # Direct call simulating dispatch
        impl.search_codebase(search_context, "pattern")
        
        mock_run.assert_called()

    @patch("ayder_cli.tools.builtins.search.shutil.which")
    @patch("ayder_cli.tools.builtins.search.subprocess.run")
    def test_dispatcher_with_kwargs(self, mock_run, mock_which, search_context):
        """Test dispatcher with keyword arguments."""
        mock_which.return_value = "/usr/bin/rg"
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        impl.search_codebase(search_context, "pattern", case_sensitive=False)
        
        cmd = mock_run.call_args[0][0]
        assert "--ignore-case" in cmd

    @patch("ayder_cli.tools.builtins.search.shutil.which")
    @patch("ayder_cli.tools.builtins.search.subprocess.run")
    def test_dispatcher_with_json_string(self, mock_run, mock_which, search_context):
        """Test dispatcher handling (simulated) for complex types."""
        # Note: Argument parsing happens before search_codebase is called in real app
        # but we can test the underlying function behavior
        mock_which.return_value = "/usr/bin/rg"
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        impl.search_codebase(search_context, "pattern")
        mock_run.assert_called()


class TestSearchFallback:
    """Test fallback mechanisms."""

    @patch("ayder_cli.tools.builtins.search.shutil.which")
    @patch("ayder_cli.tools.builtins.search.subprocess.run")
    def test_search_executes_without_error(self, mock_run, mock_which, search_context):
        """Test that search executes without raising exception."""
        mock_which.return_value = None  # Force grep fallback
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        result = impl.search_codebase(search_context, "pattern")
        assert isinstance(result, ToolSuccess)
        assert "SEARCH RESULTS" in result
