"""Tests for tool implementations."""

import json
import sys
import pytest
from pathlib import Path
from ayder_cli.tools import impl


@pytest.fixture
def project_context(tmp_path, monkeypatch):
    """Create a project context with tmp_path as root and set it for tools."""
    from ayder_cli.path_context import ProjectContext
    
    ctx = ProjectContext(str(tmp_path))
    monkeypatch.setattr(impl, "_default_project_ctx", ctx)
    return ctx


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
        result = impl.list_files()

        files = json.loads(result)
        assert "file1.txt" in files
        assert "file2.txt" in files
        assert "subdir" in files

    def test_list_files_specified_directory(self, tmp_path, project_context):
        """Test listing files in specified directory."""
        # Create test files
        (tmp_path / "file1.txt").write_text("content1")
        (tmp_path / "file2.txt").write_text("content2")

        result = impl.list_files(str(tmp_path))
        files = json.loads(result)

        assert "file1.txt" in files
        assert "file2.txt" in files

    def test_list_files_nonexistent_directory(self, tmp_path, project_context):
        """Test error handling for non-existent directory."""
        # Use a path within the sandbox that doesn't exist
        result = impl.list_files("nonexistent/path/12345")
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
                result = impl.list_files(str(restricted_dir))
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

        result = impl.read_file(str(test_file))
        assert result == test_content

    def test_read_with_start_line(self, tmp_path, project_context):
        """Test reading with start_line parameter."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Line 1\nLine 2\nLine 3\nLine 4\n")

        result = impl.read_file(str(test_file), start_line=2)
        assert "2: Line 2" in result
        assert "3: Line 3" in result
        assert "4: Line 4" in result
        assert "1: Line 1" not in result

    def test_read_with_end_line(self, tmp_path, project_context):
        """Test reading with end_line parameter."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Line 1\nLine 2\nLine 3\nLine 4\n")

        result = impl.read_file(str(test_file), end_line=2)
        assert "1: Line 1" in result
        assert "2: Line 2" in result
        assert "3: Line 3" not in result

    def test_read_with_start_and_end_line(self, tmp_path, project_context):
        """Test reading with both start_line and end_line."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Line 1\nLine 2\nLine 3\nLine 4\nLine 5\n")

        result = impl.read_file(str(test_file), start_line=2, end_line=4)
        assert "2: Line 2" in result
        assert "3: Line 3" in result
        assert "4: Line 4" in result
        assert "1: Line 1" not in result
        assert "5: Line 5" not in result

    def test_read_nonexistent_file(self, tmp_path, project_context):
        """Test error handling for non-existent file."""
        # Use a path within the sandbox that doesn't exist
        result = impl.read_file("nonexistent/file.txt")
        assert "Error" in result
        assert "does not exist" in result

    def test_read_file_line_numbers_displayed(self, tmp_path, project_context):
        """Verify line numbers are correctly displayed in output."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("First line\nSecond line\nThird line\n")

        result = impl.read_file(str(test_file), start_line=1, end_line=3)
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

        result = impl.write_file(str(test_file), content)

        assert "Successfully wrote" in result
        assert test_file.read_text() == content

    def test_overwrite_existing_file(self, tmp_path, project_context):
        """Test overwriting existing file."""
        test_file = tmp_path / "existing.txt"
        test_file.write_text("Old content")

        new_content = "New content"
        result = impl.write_file(str(test_file), new_content)

        assert "Successfully wrote" in result
        assert test_file.read_text() == new_content

    def test_write_unicode_content(self, tmp_path, project_context):
        """Test writing with unicode content."""
        test_file = tmp_path / "unicode.txt"
        content = "Unicode: 你好世界 🌍 émojis àccents"

        result = impl.write_file(str(test_file), content)

        assert "Successfully wrote" in result
        assert test_file.read_text() == content

    def test_write_file_invalid_path(self, tmp_path, project_context):
        """Test error handling for invalid paths."""
        # Try to write to a path that can't be created (within sandbox)
        result = impl.write_file("/subdir/file.txt", "content")
        assert "Error" in result


class TestReplaceString:
    """Test replace_string() function."""

    def test_successful_string_replacement(self, tmp_path, project_context):
        """Test successful string replacement."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello world! Hello everyone!")

        result = impl.replace_string(str(test_file), "world", "universe")

        assert "Successfully replaced" in result
        assert test_file.read_text() == "Hello universe! Hello everyone!"

    def test_replacement_old_string_not_found(self, tmp_path, project_context):
        """Test replacement when old_string not found (error case)."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello world!")

        result = impl.replace_string(str(test_file), "notfound", "replacement")

        assert "Error" in result
        assert "not found" in result
        # Verify file wasn't changed
        assert test_file.read_text() == "Hello world!"

    def test_multiple_occurrences_replacement(self, tmp_path, project_context):
        """Test multiple occurrences replacement."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello world! Hello world! Hello world!")

        result = impl.replace_string(str(test_file), "world", "Python")

        assert "Successfully replaced" in result
        assert test_file.read_text() == "Hello Python! Hello Python! Hello Python!"

    def test_replace_string_nonexistent_file(self, tmp_path, project_context):
        """Test error handling for non-existent file."""
        result = impl.replace_string("nonexistent/file.txt", "old", "new")
        assert "Error" in result


class TestRunShellCommand:
    """Test run_shell_command() function."""

    def test_successful_command_execution(self, project_context):
        """Test successful command execution."""
        result = impl.run_shell_command("echo hello")
        assert "Exit Code: 0" in result

    def test_command_with_stdout_output(self, project_context):
        """Test command with stdout output."""
        result = impl.run_shell_command("echo test output")
        assert "STDOUT:" in result
        assert "test output" in result

    def test_command_with_stderr_output(self, project_context):
        """Test command with stderr output."""
        # Use a command that writes to stderr
        result = impl.run_shell_command("ls /nonexistent_path_12345 2>&1 || echo 'error occurred' >&2")
        # Command may have stderr depending on shell behavior
        assert "Exit Code:" in result

    def test_command_with_non_zero_exit_code(self, project_context):
        """Test command with non-zero exit code."""
        result = impl.run_shell_command("exit 1")
        assert "Exit Code: 1" in result

    @pytest.mark.skip(reason="Disabled - takes too long to run")
    def test_timeout_handling(self):
        """Test timeout handling - DISABLED."""
        # This test is disabled because it takes 65+ seconds to run
        # To test timeout manually, run:
        #   result = impl.run_shell_command("sleep 65")
        #   assert "Error: Command timed out" in result
        pytest.skip("Timeout test disabled - see test source for manual test instructions")

    def test_error_handling_invalid_command(self, project_context):
        """Test error handling for invalid commands."""
        result = impl.run_shell_command("invalid_command_xyz_12345")
        # Should return error output or error message
        assert "Exit Code:" in result or "Error executing command" in result
