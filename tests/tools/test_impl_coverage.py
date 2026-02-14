"""Additional tests for tools/impl.py to improve coverage."""

import json
import sys
import pytest
from pathlib import Path
from unittest.mock import patch, Mock
from ayder_cli.core.context import ProjectContext
from ayder_cli.core.result import ToolSuccess, ToolError
from ayder_cli.tools import search, filesystem, shell, utils_tools, venv

# Create a namespace object that mimicks the old 'impl' module
class ImplNamespace:
    pass

impl = ImplNamespace()
impl.search_codebase = search.search_codebase
impl._search_with_ripgrep = search._search_with_ripgrep
impl._search_with_grep = search._search_with_grep
impl._format_search_results = search._format_search_results
impl._format_grep_results = search._format_grep_results
impl._format_files_only = search._format_files_only
impl._format_count_results = search._format_count_results

impl.get_project_structure = utils_tools.get_project_structure
impl._generate_manual_tree = utils_tools._generate_manual_tree
impl.manage_environment_vars = utils_tools.manage_environment_vars

impl.read_file = filesystem.read_file
impl.write_file = filesystem.write_file
impl.replace_string = filesystem.replace_string
impl.list_files = filesystem.list_files
impl.insert_line = filesystem.insert_line
impl.delete_line = filesystem.delete_line
impl.get_file_info = filesystem.get_file_info
impl.MAX_FILE_SIZE = filesystem.MAX_FILE_SIZE

impl.run_shell_command = shell.run_shell_command

impl.create_virtualenv = venv.create_virtualenv
impl.install_requirements = venv.install_requirements
impl.list_virtualenvs = venv.list_virtualenvs
impl.activate_virtualenv = venv.activate_virtualenv
impl.remove_virtualenv = venv.remove_virtualenv


class TestSearchCodebaseNoMatches:
    """Test search_codebase() with no matches found."""

    @patch("ayder_cli.tools.search.shutil.which")
    @patch("ayder_cli.tools.search.subprocess.run")
    def test_search_no_matches_ripgrep(self, mock_run, mock_which, tmp_path):
        """Test search with no matches using ripgrep."""
        mock_which.return_value = "/usr/bin/rg"
        mock_run.return_value = Mock(returncode=1, stdout="", stderr="")

        # Set up project context with tmp_path as root
        ctx = ProjectContext(str(tmp_path))

        result = impl.search_codebase(ctx, "nonexistent_pattern_xyz")

        assert isinstance(result, ToolSuccess)
        assert "No matches found" in result
        assert "nonexistent_pattern_xyz" in result

    @patch("ayder_cli.tools.search.shutil.which")
    @patch("ayder_cli.tools.search.subprocess.run")
    def test_search_no_matches_grep(self, mock_run, mock_which, tmp_path):
        """Test search with no matches using grep fallback."""
        mock_which.side_effect = lambda cmd: None if cmd == "rg" else "/usr/bin/grep"
        mock_run.return_value = Mock(returncode=1, stdout="", stderr="")

        # Set up project context with tmp_path as root
        ctx = ProjectContext(str(tmp_path))

        result = impl.search_codebase(ctx, "nonexistent_pattern_xyz")

        assert "No matches found" in result


class TestSearchCodebaseFilePatterns:
    """Test search_codebase() with various file pattern filters."""

    @patch("ayder_cli.tools.search.shutil.which")
    @patch("ayder_cli.tools.search.subprocess.run")
    def test_search_with_file_pattern(self, mock_run, mock_which, tmp_path):
        """Test search with file pattern filter."""
        mock_which.return_value = "/usr/bin/rg"
        mock_run.return_value = Mock(
            returncode=0,
            stdout="test.py\n1:def hello():\n",
            stderr=""
        )

        # Set up project context with tmp_path as root
        ctx = ProjectContext(str(tmp_path))

        result = impl.search_codebase(ctx, "def", file_pattern="*.py")

        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert "--glob" in call_args
        assert "*.py" in call_args
        assert "Matches found" in result

    @patch("ayder_cli.tools.search.shutil.which")
    @patch("ayder_cli.tools.search.subprocess.run")
    def test_search_case_insensitive(self, mock_run, mock_which, tmp_path):
        """Test search with case insensitive flag."""
        mock_which.return_value = "/usr/bin/rg"
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

        # Set up project context with tmp_path as root
        ctx = ProjectContext(str(tmp_path))

        impl.search_codebase(ctx, "HELLO", case_sensitive=False)

        call_args = mock_run.call_args[0][0]
        assert "--ignore-case" in call_args


class TestSearchCodebaseContextLines:
    """Test search_codebase() context lines functionality."""

    @patch("ayder_cli.tools.search.shutil.which")
    @patch("ayder_cli.tools.search.subprocess.run")
    def test_search_with_context_lines(self, mock_run, mock_which, tmp_path):
        """Test search with context lines."""
        mock_which.return_value = "/usr/bin/rg"
        mock_run.return_value = Mock(
            returncode=0,
            stdout="test.py\n1:def before():\n2:def target():\n3:def after():\n",
            stderr=""
        )

        # Set up project context with tmp_path as root
        ctx = ProjectContext(str(tmp_path))

        result = impl.search_codebase(ctx, "target", context_lines=2)

        call_args = mock_run.call_args[0][0]
        assert "--context" in call_args
        assert "2" in call_args


class TestSearchCodebaseErrorHandling:
    """Test search_codebase() error handling paths."""

    @patch("ayder_cli.tools.search.shutil.which")
    @patch("ayder_cli.tools.search.subprocess.run")
    def test_ripgrep_error_exit_code(self, mock_run, mock_which, tmp_path):
        """Test ripgrep failing with error exit code."""
        mock_which.return_value = "/usr/bin/rg"
        mock_run.return_value = Mock(returncode=2, stdout="", stderr="some error")

        # Set up project context with tmp_path as root
        ctx = ProjectContext(str(tmp_path))

        result = impl.search_codebase(ctx, "pattern")

        assert isinstance(result, ToolError)
        assert result.category == "execution"
        assert "Error: ripgrep failed" in result
        assert "some error" in result

    @patch("ayder_cli.tools.search.shutil.which")
    @patch("ayder_cli.tools.search.subprocess.run")
    def test_ripgrep_timeout(self, mock_run, mock_which, tmp_path):
        """Test ripgrep timeout handling."""
        mock_which.return_value = "/usr/bin/rg"
        mock_run.side_effect = Exception("Timeout")

        # Set up project context with tmp_path as root
        ctx = ProjectContext(str(tmp_path))

        result = impl.search_codebase(ctx, "pattern")

        assert "Error executing ripgrep" in result or "Error during search" in result

    @patch("ayder_cli.tools.search.shutil.which")
    def test_search_codebase_exception(self, mock_which, tmp_path):
        """Test search_codebase outer exception handler."""
        mock_which.side_effect = Exception("Unexpected error")

        # Set up project context with tmp_path as root
        ctx = ProjectContext(str(tmp_path))

        result = impl.search_codebase(ctx, "pattern")

        assert isinstance(result, ToolError)
        assert result.category == "execution"
        assert "Error during search" in result


class TestSearchWithGrepFallback:
    """Test _search_with_grep() fallback implementation."""

    @patch("ayder_cli.tools.search.shutil.which")
    @patch("ayder_cli.tools.search.subprocess.run")
    def test_grep_search_success(self, mock_run, mock_which, tmp_path):
        """Test successful grep search."""
        mock_which.side_effect = lambda cmd: None if cmd == "rg" else "/usr/bin/grep"
        mock_run.return_value = Mock(
            returncode=0,
            stdout="file.txt:1:hello world\nfile.txt:2:hello again",
            stderr=""
        )

        # Set up project context with tmp_path as root
        ctx = ProjectContext(str(tmp_path))

        result = impl.search_codebase(ctx, "hello")

        assert "SEARCH RESULTS" in result
        assert "Matches found" in result

    @patch("ayder_cli.tools.search.shutil.which")
    @patch("ayder_cli.tools.search.subprocess.run")
    def test_grep_case_insensitive(self, mock_run, mock_which, tmp_path):
        """Test grep with case insensitive flag."""
        mock_which.side_effect = lambda cmd: None if cmd == "rg" else "/usr/bin/grep"
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

        # Set up project context with tmp_path as root
        ctx = ProjectContext(str(tmp_path))

        impl.search_codebase(ctx, "HELLO", case_sensitive=False)

        call_args = mock_run.call_args[0][0]
        assert "-i" in call_args

    @patch("ayder_cli.tools.search.shutil.which")
    @patch("ayder_cli.tools.search.subprocess.run")
    def test_grep_with_context_lines(self, mock_run, mock_which, tmp_path):
        """Test grep with context lines."""
        mock_which.side_effect = lambda cmd: None if cmd == "rg" else "/usr/bin/grep"
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

        # Set up project context with tmp_path as root
        ctx = ProjectContext(str(tmp_path))

        impl.search_codebase(ctx, "pattern", context_lines=3)

        call_args = mock_run.call_args[0][0]
        assert "-C" in call_args
        assert "3" in call_args

    @patch("ayder_cli.tools.search.shutil.which")
    @patch("ayder_cli.tools.search.subprocess.run")
    def test_grep_with_file_pattern(self, mock_run, mock_which, tmp_path):
        """Test grep with file pattern."""
        mock_which.side_effect = lambda cmd: None if cmd == "rg" else "/usr/bin/grep"
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

        # Set up project context with tmp_path as root
        ctx = ProjectContext(str(tmp_path))

        impl.search_codebase(ctx, "pattern", file_pattern="src/*.py")

        call_args = mock_run.call_args[0][0]
        assert "--include" in call_args
        assert "*.py" in call_args

    @patch("ayder_cli.tools.search.shutil.which")
    @patch("ayder_cli.tools.search.subprocess.run")
    def test_grep_error_exit_code(self, mock_run, mock_which, tmp_path):
        """Test grep failing with error exit code."""
        mock_which.side_effect = lambda cmd: None if cmd == "rg" else "/usr/bin/grep"
        mock_run.return_value = Mock(returncode=2, stdout="", stderr="grep error")

        # Set up project context with tmp_path as root
        ctx = ProjectContext(str(tmp_path))

        result = impl.search_codebase(ctx, "pattern")

        assert isinstance(result, ToolError)
        assert result.category == "execution"
        assert "Error: grep failed" in result
        assert "grep error" in result

    @patch("ayder_cli.tools.search.shutil.which")
    @patch("ayder_cli.tools.search.subprocess.run")
    def test_grep_timeout(self, mock_run, mock_which, tmp_path):
        """Test grep timeout handling."""
        mock_which.side_effect = lambda cmd: None if cmd == "rg" else "/usr/bin/grep"
        mock_run.side_effect = Exception("Timeout")

        # Set up project context with tmp_path as root
        ctx = ProjectContext(str(tmp_path))

        result = impl.search_codebase(ctx, "pattern")

        assert "Error executing grep" in result or "Error during search" in result


class TestFormatGrepResults:
    """Test _format_grep_results() function."""

    def test_format_grep_results_basic(self):
        """Test basic grep result formatting."""
        from ayder_cli.core.context import ProjectContext
        project = ProjectContext(".")
        raw_output = "file1.txt:1:hello world\nfile1.txt:2:hello again\nfile2.txt:5:another match"
        result = impl._format_grep_results(raw_output, "hello", 50, project)

        assert "SEARCH RESULTS" in result
        assert "Matches found: 3" in result
        assert "FILE: file1.txt" in result
        assert "FILE: file2.txt" in result

    def test_format_grep_results_empty(self):
        """Test formatting empty grep results."""
        from ayder_cli.core.context import ProjectContext
        project = ProjectContext(".")
        result = impl._format_grep_results("", "pattern", 50, project)

        assert "SEARCH RESULTS" in result
        assert "Matches found: 0" in result

    def test_format_grep_results_max_results(self):
        """Test grep results with max_results limit."""
        from ayder_cli.core.context import ProjectContext
        project = ProjectContext(".")
        raw_output = "file.txt:1:line1\nfile.txt:2:line2\nfile.txt:3:line3"
        result = impl._format_grep_results(raw_output, "line", 2, project)

        assert "Matches found: 2" in result


class TestGetProjectStructureEdgeCases:
    """Test get_project_structure() edge cases."""

    @patch("ayder_cli.tools.utils_tools.shutil.which")
    @patch("ayder_cli.tools.utils_tools.subprocess.run")
    def test_tree_fallback_on_error(self, mock_run, mock_which, tmp_path):
        """Test fallback to manual tree when tree command fails."""
        mock_which.return_value = "/usr/bin/tree"
        mock_run.side_effect = Exception("Tree failed")
        
        ctx = ProjectContext(str(tmp_path))
        result = impl.get_project_structure(ctx, max_depth=2)

        # Should return the manual tree fallback
        assert isinstance(result, str)
        assert len(result) > 0

    @patch("ayder_cli.tools.utils_tools.shutil.which")
    def test_manual_tree_no_tree_command(self, mock_which, tmp_path):
        """Test manual tree generation when tree not available."""
        mock_which.return_value = None
        
        ctx = ProjectContext(str(tmp_path))
        result = impl.get_project_structure(ctx, max_depth=2)

        assert isinstance(result, str)

    def test_manual_tree_max_depth_variations(self, tmp_path, monkeypatch):
        """Test manual tree with different max_depth values."""
        # Create nested structure
        (tmp_path / "level1").mkdir()
        (tmp_path / "level1" / "level2").mkdir()
        (tmp_path / "level1" / "level2" / "level3").mkdir()
        (tmp_path / "file1.txt").write_text("content")

        monkeypatch.chdir(tmp_path)
        ctx = ProjectContext(str(tmp_path))

        # Test depth 1 - only root level
        result_depth1 = impl._generate_manual_tree(ctx, max_depth=1)
        lines_depth1 = result_depth1.split("\n")

        # Test depth 3 - should show more levels
        result_depth3 = impl._generate_manual_tree(ctx, max_depth=3)
        lines_depth3 = result_depth3.split("\n")

        # Depth 3 should have more lines than depth 1
        assert len(lines_depth3) >= len(lines_depth1)

    def test_manual_tree_permission_error(self, tmp_path, monkeypatch):
        """Test manual tree with permission errors."""
        # Skip on Windows
        if sys.platform == 'win32':
            pytest.skip("Permission tests not applicable on Windows")

        # Create structure with restricted directory
        (tmp_path / "restricted").mkdir()
        (tmp_path / "public").mkdir()
        (tmp_path / "public" / "file.txt").write_text("content")

        # Restrict access
        (tmp_path / "restricted").chmod(0o000)

        try:
            monkeypatch.chdir(tmp_path)
            ctx = ProjectContext(str(tmp_path))
            result = impl._generate_manual_tree(ctx, max_depth=3)
            # Should complete without error even with permission error
            assert isinstance(result, str)
        finally:
            # Restore permissions
            (tmp_path / "restricted").chmod(0o755)


class TestReadFileEdgeCases:
    """Test read_file() edge cases."""

    def test_read_file_encoding_error(self, tmp_path, monkeypatch):
        """Test read_file with encoding issues."""
        test_file = tmp_path / "binary.txt"
        # Write binary content that can't be decoded as UTF-8
        test_file.write_bytes(b"\x80\x81\x82\x83")

        # Set up project context with tmp_path as root
        ctx = ProjectContext(str(tmp_path))

        result = impl.read_file(ctx, "binary.txt")

        # Should handle encoding error gracefully - errors='replace' should be used
        assert isinstance(result, str)

    def test_read_file_start_line_beyond_file(self, tmp_path):
        """Test read_file with start_line beyond file length."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Line 1\nLine 2\n")
        
        ctx = ProjectContext(str(tmp_path))
        result = impl.read_file(ctx, str(test_file), start_line=100)

        # Should handle gracefully (empty result or adjusted)
        assert isinstance(result, str)

    def test_read_file_string_line_numbers(self, tmp_path, monkeypatch):
        """Test read_file with string line numbers (converted to int)."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Line 1\nLine 2\nLine 3\n")

        # Set up project context with tmp_path as root
        ctx = ProjectContext(str(tmp_path))

        # Pass strings instead of ints
        result = impl.read_file(ctx, "test.txt", start_line="2", end_line="3")

        assert "2: Line 2" in result
        assert "3: Line 3" in result


class TestWriteFileNestedDirectories:
    """Test write_file() with nested directory creation."""

    def test_write_file_creates_parent_directories(self, tmp_path):
        """Test write_file creates parent directories automatically."""
        # Set up project context with tmp_path as root
        ctx = ProjectContext(str(tmp_path))

        # Write to a path with nested nonexistent directories
        result = impl.write_file(ctx, "nonexistent_dir_xyz/subdir/file.txt", "content")

        # Should succeed and create directories
        assert isinstance(result, ToolSuccess)
        assert "Successfully wrote" in result

        # Verify file was created
        created_file = tmp_path / "nonexistent_dir_xyz" / "subdir" / "file.txt"
        assert created_file.exists()
        assert created_file.read_text() == "content"


class TestReplaceStringEdgeCases:
    """Test replace_string() edge cases."""

    def test_replace_string_empty_file(self, tmp_path, monkeypatch):
        """Test replace_string with empty file."""
        test_file = tmp_path / "empty.txt"
        test_file.write_text("")

        # Set up project context with tmp_path as root
        ctx = ProjectContext(str(tmp_path))

        result = impl.replace_string(ctx, "empty.txt", "old", "new")

        assert "not found" in result
        assert test_file.read_text() == ""


class TestListFilesSymlinks:
    """Test list_files() with symlinks."""

    def test_list_files_with_symlink(self, tmp_path, monkeypatch):
        """Test listing files including symlinks."""
        # Skip on Windows
        if sys.platform == 'win32':
            pytest.skip("Symlink tests not applicable on Windows")

        test_file = tmp_path / "real_file.txt"
        test_file.write_text("content")
        symlink = tmp_path / "link_file.txt"
        symlink.symlink_to(test_file)

        # Set up project context with tmp_path as root
        ctx = ProjectContext(str(tmp_path))

        result = impl.list_files(ctx, ".")
        files = json.loads(result)

        assert "real_file.txt" in files
        assert "link_file.txt" in files


class TestRunShellCommandTimeout:
    """Test run_shell_command() timeout handling."""

    @patch("ayder_cli.tools.shell.subprocess.run")
    def test_run_shell_command_timeout(self, mock_run, tmp_path):
        """Test run_shell_command timeout handling."""
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="sleep 100", timeout=60)

        ctx = ProjectContext(str(tmp_path))
        result = impl.run_shell_command(ctx, "sleep 100")

        assert isinstance(result, ToolError)
        assert result.category == "execution"
        assert "timed out" in result.lower()