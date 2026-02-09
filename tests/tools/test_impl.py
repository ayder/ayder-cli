"""Tests for tool implementations."""

import json
import sys
import subprocess
import shutil
from unittest.mock import patch, MagicMock
import pytest
from pathlib import Path
from ayder_cli.tools import impl
from ayder_cli.core.context import ProjectContext
from ayder_cli.core.result import ToolSuccess, ToolError


@pytest.fixture
def project_context(tmp_path):
    """Create a project context with tmp_path as root."""
    return ProjectContext(str(tmp_path))


class TestListFiles:
    """Test list_files() function."""

    def test_list_files_current_directory(self, tmp_path, monkeypatch, project_context):
        """Test listing files in current directory."""
        # Create test files in tmp_path
        (tmp_path / "file1.txt").write_text("content1")
        (tmp_path / "file2.txt").write_text("content2")
        (tmp_path / "subdir").mkdir()

        # Change to tmp_path and test with default (current directory)
        monkeypatch.chdir(tmp_path)
        result = impl.list_files(project_context)

        assert isinstance(result, ToolSuccess)
        files = json.loads(result)
        assert "file1.txt" in files
        assert "file2.txt" in files
        assert "subdir" in files

    def test_list_files_specified_directory(self, tmp_path, project_context):
        """Test listing files in specified directory."""
        # Create test files
        (tmp_path / "file1.txt").write_text("content1")
        (tmp_path / "file2.txt").write_text("content2")

        result = impl.list_files(project_context, str(tmp_path))
        files = json.loads(result)

        assert "file1.txt" in files
        assert "file2.txt" in files

    def test_list_files_nonexistent_directory(self, tmp_path, project_context):
        """Test error handling for non-existent directory."""
        # Use a path within the sandbox that doesn't exist
        result = impl.list_files(project_context, "nonexistent/path/12345")
        assert isinstance(result, ToolError)
        assert "Error" in result

    def test_list_files_permission_error(self, tmp_path, project_context):
        """Test error handling for permission errors."""
        # Create a directory and remove read permissions
        restricted_dir = tmp_path / "restricted"
        restricted_dir.mkdir()

        # Skip on Windows as permission model is different
        if sys.platform != 'win32':
            restricted_dir.chmod(0o000)
            try:
                result = impl.list_files(project_context, str(restricted_dir))
                assert isinstance(result, ToolError)
                assert result.category == "execution"
                assert "Error listing files" in result
            finally:
                # Restore permissions for cleanup
                restricted_dir.chmod(0o755)


class TestReadFile:
    """Test read_file() function."""

    def test_read_entire_file(self, tmp_path, project_context):
        """Test reading entire file."""
        test_file = tmp_path / "test.txt"
        test_content = "Line 1\nLine 2\nLine 3\n"
        test_file.write_text(test_content)

        result = impl.read_file(project_context, str(test_file))
        assert isinstance(result, ToolSuccess)
        assert result == test_content

    def test_read_with_start_line(self, tmp_path, project_context):
        """Test reading with start_line parameter."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Line 1\nLine 2\nLine 3\nLine 4\n")

        result = impl.read_file(project_context, str(test_file), start_line=2)
        assert "2: Line 2" in result
        assert "3: Line 3" in result
        assert "4: Line 4" in result
        assert "1: Line 1" not in result

    def test_read_with_end_line(self, tmp_path, project_context):
        """Test reading with end_line parameter."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Line 1\nLine 2\nLine 3\nLine 4\n")

        result = impl.read_file(project_context, str(test_file), end_line=2)
        assert "1: Line 1" in result
        assert "2: Line 2" in result
        assert "3: Line 3" not in result

    def test_read_with_start_and_end_line(self, tmp_path, project_context):
        """Test reading with both start_line and end_line."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Line 1\nLine 2\nLine 3\nLine 4\nLine 5\n")

        result = impl.read_file(project_context, str(test_file), start_line=2, end_line=4)
        assert "2: Line 2" in result
        assert "3: Line 3" in result
        assert "4: Line 4" in result
        assert "1: Line 1" not in result
        assert "5: Line 5" not in result

    def test_read_nonexistent_file(self, tmp_path, project_context):
        """Test error handling for non-existent file."""
        # Use a path within the sandbox that doesn't exist
        result = impl.read_file(project_context, "nonexistent/file.txt")
        assert isinstance(result, ToolError)
        assert "Error" in result
        assert "does not exist" in result

    def test_read_file_line_numbers_displayed(self, tmp_path, project_context):
        """Verify line numbers are correctly displayed in output."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("First line\nSecond line\nThird line\n")

        result = impl.read_file(project_context, str(test_file), start_line=1, end_line=3)
        # Check that line numbers are present
        assert "1: First line" in result
        assert "2: Second line" in result
        assert "3: Third line" in result


class TestWriteFile:
    """Test write_file() function."""

    def test_write_new_file(self, tmp_path, project_context):
        """Test writing new file."""
        test_file = tmp_path / "new_file.txt"
        content = "This is new content"

        result = impl.write_file(project_context, str(test_file), content)

        assert isinstance(result, ToolSuccess)
        assert "Successfully wrote" in result
        assert test_file.read_text() == content

    def test_overwrite_existing_file(self, tmp_path, project_context):
        """Test overwriting existing file."""
        test_file = tmp_path / "existing.txt"
        test_file.write_text("Old content")

        new_content = "New content"
        result = impl.write_file(project_context, str(test_file), new_content)

        assert "Successfully wrote" in result
        assert test_file.read_text() == new_content

    def test_write_unicode_content(self, tmp_path, project_context):
        """Test writing with unicode content."""
        test_file = tmp_path / "unicode.txt"
        content = "Unicode: 你好世界 🌍 émojis àccents"

        result = impl.write_file(project_context, str(test_file), content)

        assert "Successfully wrote" in result
        assert test_file.read_text() == content

    def test_write_file_invalid_path(self, tmp_path, project_context):
        """Test error handling for invalid paths."""
        # Try to write to a path that can't be created (within sandbox)
        result = impl.write_file(project_context, "/subdir/file.txt", "content")
        assert isinstance(result, ToolError)
        assert "Error" in result


class TestReplaceString:
    """Test replace_string() function."""

    def test_successful_string_replacement(self, tmp_path, project_context):
        """Test successful string replacement."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello world! Hello everyone!")

        result = impl.replace_string(project_context, str(test_file), "world", "universe")

        assert isinstance(result, ToolSuccess)
        assert "Successfully replaced" in result
        assert test_file.read_text() == "Hello universe! Hello everyone!"

    def test_replacement_old_string_not_found(self, tmp_path, project_context):
        """Test replacement when old_string not found (error case)."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello world!")

        result = impl.replace_string(project_context, str(test_file), "notfound", "replacement")

        assert isinstance(result, ToolError)
        assert "Error" in result
        assert "not found" in result
        # Verify file wasn't changed
        assert test_file.read_text() == "Hello world!"

    def test_multiple_occurrences_replacement(self, tmp_path, project_context):
        """Test multiple occurrences replacement."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello world! Hello world! Hello world!")

        result = impl.replace_string(project_context, str(test_file), "world", "Python")

        assert "Successfully replaced" in result
        assert test_file.read_text() == "Hello Python! Hello Python! Hello Python!"

    def test_replace_string_nonexistent_file(self, tmp_path, project_context):
        """Test error handling for non-existent file."""
        result = impl.replace_string(project_context, "nonexistent/file.txt", "old", "new")
        assert "Error" in result


class TestRunShellCommand:
    """Test run_shell_command() function."""

    def test_successful_command_execution(self, project_context):
        """Test successful command execution."""
        result = impl.run_shell_command(project_context, "echo hello")
        assert isinstance(result, ToolSuccess)
        assert "Exit Code: 0" in result

    def test_command_with_stdout_output(self, project_context):
        """Test command with stdout output."""
        result = impl.run_shell_command(project_context, "echo test output")
        assert "STDOUT:" in result
        assert "test output" in result

    def test_command_with_stderr_output(self, project_context):
        """Test command with stderr output."""
        # Use a command that writes to stderr
        result = impl.run_shell_command(project_context, "ls /nonexistent_path_12345 2>&1 || echo 'error occurred' >&2")
        # Command may have stderr depending on shell behavior
        assert "Exit Code:" in result

    def test_command_with_non_zero_exit_code(self, project_context):
        """Test command with non-zero exit code."""
        result = impl.run_shell_command(project_context, "exit 1")
        assert "Exit Code: 1" in result

    def test_error_handling_invalid_command(self, project_context):
        """Test error handling for invalid commands."""
        result = impl.run_shell_command(project_context, "invalid_command_xyz_12345")
        # Should return error output or error message
        assert "Exit Code:" in result or "Error executing command" in result


class TestRunShellCommandExceptions:
    """Test exception handling in run_shell_command - Lines 205-206."""

    def test_exception_handling_general_error(self, project_context):
        """Test general exception handling - Lines 205-206."""
        with patch('subprocess.run', side_effect=OSError("Mocked OS error")):
            result = impl.run_shell_command(project_context, "echo test")
            assert isinstance(result, ToolError)
            assert result.category == "execution"
            assert "Error executing command" in result
            assert "Mocked OS error" in result


class TestReadFileSizeLimit:
    """Test file size limit in read_file - FIX-002."""

    def test_read_file_rejects_oversized_file(self, tmp_path, project_context, monkeypatch):
        """Test that files exceeding MAX_FILE_SIZE are rejected with descriptive error."""
        # Temporarily set a small max size for testing
        monkeypatch.setattr(impl, "MAX_FILE_SIZE", 100)  # 100 bytes limit

        test_file = tmp_path / "large_file.txt"
        # Create content larger than the limit
        large_content = "x" * 200  # 200 bytes
        test_file.write_text(large_content)

        result = impl.read_file(project_context, str(test_file))

        # Should return an error message, not an exception
        assert isinstance(result, ToolError)
        assert "Error" in result
        assert "too large" in result.lower()
        assert "0.0MB" in result or "0.2KB" in result or "200 bytes" in result.lower()
        assert "Maximum allowed size" in result

    def test_read_file_accepts_normal_size_file(self, tmp_path, project_context, monkeypatch):
        """Test that normal-sized files are read successfully."""
        # Temporarily set a small max size for testing
        monkeypatch.setattr(impl, "MAX_FILE_SIZE", 1024)  # 1KB limit
        
        test_file = tmp_path / "normal_file.txt"
        normal_content = "This is a normal file content."
        test_file.write_text(normal_content)
        
        result = impl.read_file(project_context, str(test_file))
        
        # Should return the file content successfully
        assert result == normal_content
        assert "Error" not in result

    def test_read_file_size_limit_exact_boundary(self, tmp_path, project_context, monkeypatch):
        """Test that files exactly at the size limit are accepted."""
        # Set a small max size for testing
        monkeypatch.setattr(impl, "MAX_FILE_SIZE", 100)  # 100 bytes limit
        
        test_file = tmp_path / "boundary_file.txt"
        # Create content exactly at the limit
        exact_content = "x" * 100  # Exactly 100 bytes
        test_file.write_text(exact_content)
        
        result = impl.read_file(project_context, str(test_file))
        
        # Should return the file content successfully (at limit is allowed)
        assert result == exact_content
        assert "Error" not in result

    def test_read_file_size_limit_one_byte_over(self, tmp_path, project_context, monkeypatch):
        """Test that files one byte over the limit are rejected."""
        # Set a small max size for testing
        monkeypatch.setattr(impl, "MAX_FILE_SIZE", 100)  # 100 bytes limit
        
        test_file = tmp_path / "over_limit_file.txt"
        # Create content one byte over the limit
        over_limit_content = "x" * 101  # 101 bytes
        test_file.write_text(over_limit_content)
        
        result = impl.read_file(project_context, str(test_file))
        
        # Should return an error message
        assert "Error" in result
        assert "too large" in result.lower()


class TestReadFileExceptions:
    """Test exception handling in read_file - Lines 90-91."""

    def test_read_file_general_exception(self, tmp_path, project_context):
        """Test general exception handling in read_file."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        with patch('builtins.open', side_effect=IOError("Mocked IO error")):
            result = impl.read_file(project_context, str(test_file))
            assert isinstance(result, ToolError)
            assert result.category == "execution"
            assert "Error reading file" in result
            assert "Mocked IO error" in result


class TestWriteFileExceptions:
    """Test exception handling in write_file - Lines 108-109."""

    def test_write_file_general_exception(self, tmp_path, project_context):
        """Test general exception handling in write_file."""
        with patch('builtins.open', side_effect=PermissionError("Permission denied")):
            result = impl.write_file(project_context, "test.txt", "content")
            assert isinstance(result, ToolError)
            assert result.category == "execution"
            assert "Error writing file" in result
            assert "Permission denied" in result


class TestReplaceStringExceptions:
    """Test exception handling in replace_string - Lines 162-163."""

    def test_replace_string_general_exception(self, tmp_path, project_context):
        """Test general exception handling in replace_string."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        with patch('builtins.open', side_effect=IOError("Mocked IO error")):
            result = impl.replace_string(project_context, str(test_file), "old", "new")
            assert isinstance(result, ToolError)
            assert result.category == "execution"
            assert "Error replacing text" in result
            assert "Mocked IO error" in result


class TestSearchCodebaseErrors:
    """Test error handling in search_codebase - Lines 239-240, 248, 252-253."""

    def test_search_codebase_path_not_directory(self, tmp_path, project_context):
        """Test error when path is not a directory - Lines 239-240."""
        # Create a file
        test_file = tmp_path / "not_a_dir.txt"
        test_file.write_text("content")

        result = impl.search_codebase(project_context, "pattern", directory="not_a_dir.txt")
        assert isinstance(result, ToolError)
        assert "Error" in result
        assert "is not a directory" in result

    def test_search_codebase_value_error_security(self, tmp_path, project_context):
        """Test ValueError handling for security errors - Lines 252-253."""
        result = impl.search_codebase(project_context, "pattern", directory="/etc")
        assert isinstance(result, ToolError)
        assert result.category == "security"
        assert "Security Error" in result

    def test_search_codebase_general_exception(self, tmp_path, project_context):
        """Test general exception handling - Line 248."""
        # Mock validate_path to raise an exception
        project_context.validate_path = MagicMock(side_effect=RuntimeError("Mocked error"))

        result = impl.search_codebase(project_context, "pattern")
        assert isinstance(result, ToolError)
        assert result.category == "execution"
        assert "Error during search" in result


class TestSearchWithRipgrepErrors:
    """Test _search_with_ripgrep error paths - Lines 283-287."""

    def test_ripgrep_non_zero_exit(self, tmp_path, project_context):
        """Test ripgrep non-zero exit code handling - Line 283."""
        with patch('shutil.which', return_value='/usr/bin/rg'):
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = MagicMock(returncode=2, stderr="Mocked error")
                
                result = impl._search_with_ripgrep(
                    "pattern", None, True, 0, 50, tmp_path, project_context
                )
                assert isinstance(result, ToolError)
                assert result.category == "execution"
                assert "Error: ripgrep failed" in result
                assert "exit code 2" in result

    def test_ripgrep_timeout(self, tmp_path, project_context):
        """Test ripgrep timeout handling - Lines 284-285."""
        with patch('shutil.which', return_value='/usr/bin/rg'):
            with patch('subprocess.run', side_effect=subprocess.TimeoutExpired("cmd", 60)):
                result = impl._search_with_ripgrep(
                    "pattern", None, True, 0, 50, tmp_path, project_context
                )
                assert isinstance(result, ToolError)
                assert result.category == "execution"
                assert "Search timed out" in result

    def test_ripgrep_general_exception(self, tmp_path, project_context):
        """Test ripgrep general exception handling - Lines 286-287."""
        with patch('shutil.which', return_value='/usr/bin/rg'):
            with patch('subprocess.run', side_effect=OSError("Mocked error")):
                result = impl._search_with_ripgrep(
                    "pattern", None, True, 0, 50, tmp_path, project_context
                )
                assert isinstance(result, ToolError)
                assert result.category == "execution"
                assert "Error executing ripgrep" in result


class TestSearchWithGrepFallback:
    """Test _search_with_grep fallback - Lines 293-325."""

    def test_grep_fallback_used_when_no_ripgrep(self, tmp_path, project_context):
        """Test grep fallback when ripgrep is not available - Lines 293-325."""
        # Create a test file with content
        test_file = tmp_path / "test.py"
        test_file.write_text("def hello():\n    print('hello')\n")
        
        # Mock shutil.which to return None for rg (ripgrep not found)
        with patch('shutil.which', return_value=None):
            result = impl.search_codebase(project_context, "hello", directory=str(tmp_path))
            # Should use grep fallback and find the pattern
            assert "SEARCH RESULTS" in result

    def test_grep_no_matches(self, tmp_path, project_context):
        """Test grep when no matches found - Line 319."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="")

            result = impl._search_with_grep(
                "nonexistent_pattern", None, True, 0, 50, tmp_path, project_context
            )
            assert isinstance(result, ToolSuccess)
            assert "No matches found" in result

    def test_grep_non_zero_exit(self, tmp_path, project_context):
        """Test grep non-zero exit code handling - Line 321."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=2, stderr="Mocked grep error")

            result = impl._search_with_grep(
                "pattern", None, True, 0, 50, tmp_path, project_context
            )
            assert isinstance(result, ToolError)
            assert result.category == "execution"
            assert "Error: grep failed" in result
            assert "exit code 2" in result

    def test_grep_timeout(self, tmp_path, project_context):
        """Test grep timeout handling - Lines 322-323."""
        with patch('subprocess.run', side_effect=subprocess.TimeoutExpired("cmd", 60)):
            result = impl._search_with_grep(
                "pattern", None, True, 0, 50, tmp_path, project_context
            )
            assert isinstance(result, ToolError)
            assert result.category == "execution"
            assert "Search timed out" in result

    def test_grep_general_exception(self, tmp_path, project_context):
        """Test grep general exception handling - Lines 324-325."""
        with patch('subprocess.run', side_effect=OSError("Mocked error")):
            result = impl._search_with_grep(
                "pattern", None, True, 0, 50, tmp_path, project_context
            )
            assert isinstance(result, ToolError)
            assert result.category == "execution"
            assert "Error executing grep" in result


class TestFormatSearchResultsErrors:
    """Test error handling in _format_search_results - Lines 351-352."""

    def test_format_search_results_path_conversion_error(self, tmp_path, project_context):
        """Test path conversion error handling in _format_search_results."""
        # Create raw output with a path that will cause conversion issues
        raw_output = "/some/random/path.py\n1: print('hello')\n"
        
        result = impl._format_search_results(raw_output, "pattern", 50, project_context)
        
        # Should still format without crashing
        assert "SEARCH RESULTS" in result
        assert "Pattern:" in result


class TestInsertLine:
    """Test insert_line() function."""

    def test_insert_at_beginning(self, tmp_path, project_context):
        """Test inserting at line 1."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Line 1\nLine 2\nLine 3\n")

        result = impl.insert_line(project_context, str(test_file), 1, "Inserted")
        assert isinstance(result, ToolSuccess)
        assert "Successfully inserted" in result
        assert test_file.read_text() == "Inserted\nLine 1\nLine 2\nLine 3\n"

    def test_insert_in_middle(self, tmp_path, project_context):
        """Test inserting in the middle."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Line 1\nLine 2\nLine 3\n")

        result = impl.insert_line(project_context, str(test_file), 2, "Inserted")
        assert isinstance(result, ToolSuccess)
        assert test_file.read_text() == "Line 1\nInserted\nLine 2\nLine 3\n"

    def test_insert_at_end(self, tmp_path, project_context):
        """Test inserting at end (clamp)."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Line 1\nLine 2\n")

        result = impl.insert_line(project_context, str(test_file), 100, "Appended")
        assert isinstance(result, ToolSuccess)
        assert test_file.read_text() == "Line 1\nLine 2\nAppended\n"

    def test_insert_line_zero_rejected(self, tmp_path, project_context):
        """Test that line_number 0 is rejected."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Line 1\n")

        result = impl.insert_line(project_context, str(test_file), 0, "bad")
        assert isinstance(result, ToolError)
        assert result.category == "validation"

    def test_insert_nonexistent_file(self, tmp_path, project_context):
        """Test inserting into nonexistent file."""
        result = impl.insert_line(project_context, "nonexistent.txt", 1, "content")
        assert isinstance(result, ToolError)
        assert "does not exist" in result

    def test_insert_path_traversal(self, tmp_path):
        """Test path traversal is blocked."""
        ctx = ProjectContext(str(tmp_path))
        result = impl.insert_line(ctx, "../outside.txt", 1, "content")
        assert isinstance(result, ToolError)
        assert result.category == "security"

    def test_insert_adds_trailing_newline(self, tmp_path, project_context):
        """Test that content without trailing newline gets one added."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Line 1\n")

        result = impl.insert_line(project_context, str(test_file), 1, "No newline")
        assert isinstance(result, ToolSuccess)
        assert test_file.read_text() == "No newline\nLine 1\n"


class TestDeleteLine:
    """Test delete_line() function."""

    def test_delete_first_line(self, tmp_path, project_context):
        """Test deleting the first line."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Line 1\nLine 2\nLine 3\n")

        result = impl.delete_line(project_context, str(test_file), 1)
        assert isinstance(result, ToolSuccess)
        assert "Deleted line 1" in result
        assert "Line 1" in result  # preview of deleted content
        assert test_file.read_text() == "Line 2\nLine 3\n"

    def test_delete_middle_line(self, tmp_path, project_context):
        """Test deleting a middle line."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Line 1\nLine 2\nLine 3\n")

        result = impl.delete_line(project_context, str(test_file), 2)
        assert isinstance(result, ToolSuccess)
        assert test_file.read_text() == "Line 1\nLine 3\n"

    def test_delete_last_line(self, tmp_path, project_context):
        """Test deleting the last line."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Line 1\nLine 2\nLine 3\n")

        result = impl.delete_line(project_context, str(test_file), 3)
        assert isinstance(result, ToolSuccess)
        assert test_file.read_text() == "Line 1\nLine 2\n"

    def test_delete_out_of_range(self, tmp_path, project_context):
        """Test deleting beyond file length."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Line 1\nLine 2\n")

        result = impl.delete_line(project_context, str(test_file), 5)
        assert isinstance(result, ToolError)
        assert result.category == "validation"
        assert "out of range" in result

    def test_delete_line_zero_rejected(self, tmp_path, project_context):
        """Test that line_number 0 is rejected."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Line 1\n")

        result = impl.delete_line(project_context, str(test_file), 0)
        assert isinstance(result, ToolError)
        assert result.category == "validation"

    def test_delete_nonexistent_file(self, tmp_path, project_context):
        """Test deleting from nonexistent file."""
        result = impl.delete_line(project_context, "nonexistent.txt", 1)
        assert isinstance(result, ToolError)
        assert "does not exist" in result

    def test_delete_path_traversal(self, tmp_path):
        """Test path traversal is blocked."""
        ctx = ProjectContext(str(tmp_path))
        result = impl.delete_line(ctx, "../outside.txt", 1)
        assert isinstance(result, ToolError)
        assert result.category == "security"


class TestGetFileInfo:
    """Test get_file_info() function."""

    def test_file_info_basic(self, tmp_path, project_context):
        """Test basic file info."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Line 1\nLine 2\nLine 3\n")

        result = impl.get_file_info(project_context, str(test_file))
        assert isinstance(result, ToolSuccess)
        info = json.loads(result)
        assert info["line_count"] == 3
        assert info["extension"] == ".txt"
        assert info["is_file"] is True
        assert info["is_directory"] is False
        assert info["size_bytes"] > 0

    def test_file_info_directory(self, tmp_path, project_context):
        """Test directory info."""
        subdir = tmp_path / "subdir"
        subdir.mkdir()

        result = impl.get_file_info(project_context, str(subdir))
        assert isinstance(result, ToolSuccess)
        info = json.loads(result)
        assert info["is_directory"] is True
        assert info["is_file"] is False
        assert info["line_count"] is None

    def test_file_info_nonexistent(self, tmp_path, project_context):
        """Test nonexistent file."""
        result = impl.get_file_info(project_context, "nonexistent.txt")
        assert isinstance(result, ToolError)
        assert "does not exist" in result

    def test_file_info_size_human_bytes(self, tmp_path, project_context):
        """Test human-readable size for small files."""
        test_file = tmp_path / "small.txt"
        test_file.write_text("hi")

        result = impl.get_file_info(project_context, str(test_file))
        info = json.loads(result)
        assert "B" in info["size_human"]

    def test_file_info_path_traversal(self, tmp_path):
        """Test path traversal is blocked."""
        ctx = ProjectContext(str(tmp_path))
        result = impl.get_file_info(ctx, "../outside.txt")
        assert isinstance(result, ToolError)
        assert result.category == "security"

    def test_file_info_no_extension(self, tmp_path, project_context):
        """Test file with no extension."""
        test_file = tmp_path / "Makefile"
        test_file.write_text("all:\n\techo hello\n")

        result = impl.get_file_info(project_context, str(test_file))
        info = json.loads(result)
        assert info["extension"] is None or info["extension"] == ""


class TestFormatGrepResultsErrors:
    """Test error handling in _format_grep_results - Lines 391-392."""

    def test_format_grep_results_path_conversion_error(self, tmp_path, project_context):
        """Test path conversion error handling in _format_grep_results."""
        # Create raw output with a path that will cause conversion issues
        raw_output = "/some/random/path.py:1:print('hello')\n"

        result = impl._format_grep_results(raw_output, "pattern", 50, project_context)

        # Should still format without crashing
        assert "SEARCH RESULTS" in result
        assert "Pattern:" in result


class TestSearchOutputFormats:
    """Test search_codebase output_format parameter."""

    def test_format_files_only(self, tmp_path, project_context):
        """Test _format_files_only helper."""
        raw = f"{tmp_path}/file1.py\n{tmp_path}/file2.py\n"
        result = impl._format_files_only(raw, "pattern", project_context)
        assert "Files with matches: 2" in result
        assert "SEARCH RESULTS" in result

    def test_format_count_results(self, tmp_path, project_context):
        """Test _format_count_results helper."""
        raw = f"{tmp_path}/file1.py:5\n{tmp_path}/file2.py:3\n"
        result = impl._format_count_results(raw, "pattern", project_context)
        assert "Total matches: 8" in result
        assert "SEARCH RESULTS" in result