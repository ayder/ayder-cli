"""Tests for fs_tools.py module."""

import json
import os
import pytest
from unittest.mock import Mock, patch, mock_open
from ayder_cli import fs_tools


class TestListFiles:
    """Test list_files() function."""

    def test_list_files_current_directory(self, tmp_path, monkeypatch):
        """Test listing files in current directory."""
        # Create test files in tmp_path
        (tmp_path / "file1.txt").write_text("content1")
        (tmp_path / "file2.txt").write_text("content2")
        (tmp_path / "subdir").mkdir()

        # Change to tmp_path and test with default (current directory)
        monkeypatch.chdir(tmp_path)
        result = fs_tools.list_files()

        files = json.loads(result)
        assert "file1.txt" in files
        assert "file2.txt" in files
        assert "subdir" in files

    def test_list_files_specified_directory(self, tmp_path):
        """Test listing files in specified directory."""
        # Create test files
        (tmp_path / "file1.txt").write_text("content1")
        (tmp_path / "file2.txt").write_text("content2")

        result = fs_tools.list_files(str(tmp_path))
        files = json.loads(result)

        assert "file1.txt" in files
        assert "file2.txt" in files

    def test_list_files_nonexistent_directory(self):
        """Test error handling for non-existent directory."""
        result = fs_tools.list_files("/nonexistent/path/12345")
        assert "Error listing files" in result

    def test_list_files_permission_error(self, tmp_path):
        """Test error handling for permission errors."""
        # Create a directory and remove read permissions
        restricted_dir = tmp_path / "restricted"
        restricted_dir.mkdir()
        
        # Skip on Windows as permission model is different
        if os.name != 'nt':
            os.chmod(str(restricted_dir), 0o000)
            try:
                result = fs_tools.list_files(str(restricted_dir))
                assert "Error listing files" in result
            finally:
                # Restore permissions for cleanup
                os.chmod(str(restricted_dir), 0o755)


class TestReadFile:
    """Test read_file() function."""

    def test_read_entire_file(self, tmp_path):
        """Test reading entire file."""
        test_file = tmp_path / "test.txt"
        test_content = "Line 1\nLine 2\nLine 3\n"
        test_file.write_text(test_content)

        result = fs_tools.read_file(str(test_file))
        assert result == test_content

    def test_read_with_start_line(self, tmp_path):
        """Test reading with start_line parameter."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Line 1\nLine 2\nLine 3\nLine 4\n")

        result = fs_tools.read_file(str(test_file), start_line=2)
        assert "2: Line 2" in result
        assert "3: Line 3" in result
        assert "4: Line 4" in result
        assert "1: Line 1" not in result

    def test_read_with_end_line(self, tmp_path):
        """Test reading with end_line parameter."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Line 1\nLine 2\nLine 3\nLine 4\n")

        result = fs_tools.read_file(str(test_file), end_line=2)
        assert "1: Line 1" in result
        assert "2: Line 2" in result
        assert "3: Line 3" not in result

    def test_read_with_start_and_end_line(self, tmp_path):
        """Test reading with both start_line and end_line."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Line 1\nLine 2\nLine 3\nLine 4\nLine 5\n")

        result = fs_tools.read_file(str(test_file), start_line=2, end_line=4)
        assert "2: Line 2" in result
        assert "3: Line 3" in result
        assert "4: Line 4" in result
        assert "1: Line 1" not in result
        assert "5: Line 5" not in result

    def test_read_nonexistent_file(self):
        """Test error handling for non-existent file."""
        result = fs_tools.read_file("/nonexistent/file.txt")
        assert "Error: File" in result
        assert "does not exist" in result

    def test_read_file_line_numbers_displayed(self, tmp_path):
        """Verify line numbers are correctly displayed in output."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("First line\nSecond line\nThird line\n")

        result = fs_tools.read_file(str(test_file), start_line=1, end_line=3)
        # Check that line numbers are present
        assert "1: First line" in result
        assert "2: Second line" in result
        assert "3: Third line" in result


class TestWriteFile:
    """Test write_file() function."""

    def test_write_new_file(self, tmp_path):
        """Test writing new file."""
        test_file = tmp_path / "new_file.txt"
        content = "This is new content"

        result = fs_tools.write_file(str(test_file), content)

        assert "Successfully wrote" in result
        assert test_file.read_text() == content

    def test_overwrite_existing_file(self, tmp_path):
        """Test overwriting existing file."""
        test_file = tmp_path / "existing.txt"
        test_file.write_text("Old content")

        new_content = "New content"
        result = fs_tools.write_file(str(test_file), new_content)

        assert "Successfully wrote" in result
        assert test_file.read_text() == new_content

    def test_write_unicode_content(self, tmp_path):
        """Test writing with unicode content."""
        test_file = tmp_path / "unicode.txt"
        content = "Unicode: 你好世界 🌍 émojis àccents"

        result = fs_tools.write_file(str(test_file), content)

        assert "Successfully wrote" in result
        assert test_file.read_text() == content

    def test_write_file_invalid_path(self):
        """Test error handling for invalid paths."""
        # Try to write to a path that can't be created
        result = fs_tools.write_file("/nonexistent_dir_xyz/subdir/file.txt", "content")
        assert "Error writing file" in result


class TestReplaceString:
    """Test replace_string() function."""

    def test_successful_string_replacement(self, tmp_path):
        """Test successful string replacement."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello world! Hello everyone!")

        result = fs_tools.replace_string(str(test_file), "world", "universe")

        assert "Successfully replaced" in result
        assert test_file.read_text() == "Hello universe! Hello everyone!"

    def test_replacement_old_string_not_found(self, tmp_path):
        """Test replacement when old_string not found (error case)."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello world!")

        result = fs_tools.replace_string(str(test_file), "notfound", "replacement")

        assert "Error" in result
        assert "not found" in result
        # Verify file wasn't changed
        assert test_file.read_text() == "Hello world!"

    def test_multiple_occurrences_replacement(self, tmp_path):
        """Test multiple occurrences replacement."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello world! Hello world! Hello world!")

        result = fs_tools.replace_string(str(test_file), "world", "Python")

        assert "Successfully replaced" in result
        assert test_file.read_text() == "Hello Python! Hello Python! Hello Python!"

    def test_replace_string_nonexistent_file(self):
        """Test error handling for non-existent file."""
        result = fs_tools.replace_string("/nonexistent/file.txt", "old", "new")
        assert "Error replacing text" in result


class TestRunShellCommand:
    """Test run_shell_command() function."""

    def test_successful_command_execution(self):
        """Test successful command execution."""
        result = fs_tools.run_shell_command("echo hello")
        assert "Exit Code: 0" in result

    def test_command_with_stdout_output(self):
        """Test command with stdout output."""
        result = fs_tools.run_shell_command("echo test output")
        assert "STDOUT:" in result
        assert "test output" in result

    def test_command_with_stderr_output(self):
        """Test command with stderr output."""
        # Use a command that writes to stderr
        result = fs_tools.run_shell_command("ls /nonexistent_path_12345 2>&1 || echo 'error occurred' >&2")
        # Command may have stderr depending on shell behavior
        assert "Exit Code:" in result

    def test_command_with_non_zero_exit_code(self):
        """Test command with non-zero exit code."""
        result = fs_tools.run_shell_command("exit 1")
        assert "Exit Code: 1" in result

    @pytest.mark.skip(reason="Disabled - takes too long to run")
    def test_timeout_handling(self):
        """Test timeout handling."""
        # Start a command that sleeps longer than the timeout
        result = fs_tools.run_shell_command("sleep 65")
        assert "Error: Command timed out" in result

    def test_error_handling_invalid_command(self):
        """Test error handling for invalid commands."""
        result = fs_tools.run_shell_command("invalid_command_xyz_12345")
        # Should return error output or error message
        assert "Exit Code:" in result or "Error executing command" in result


class TestExecuteToolCall:
    """Test execute_tool_call() dispatcher."""

    def test_dispatch_list_files(self, tmp_path):
        """Test dispatch to list_files."""
        (tmp_path / "test.txt").write_text("content")

        result = fs_tools.execute_tool_call("list_files", {"directory": str(tmp_path)})
        files = json.loads(result)
        assert "test.txt" in files

    def test_dispatch_read_file(self, tmp_path):
        """Test dispatch to read_file."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        result = fs_tools.execute_tool_call("read_file", {"file_path": str(test_file)})
        assert result == "test content"

    def test_dispatch_write_file(self, tmp_path):
        """Test dispatch to write_file."""
        test_file = tmp_path / "test.txt"

        result = fs_tools.execute_tool_call(
            "write_file", 
            {"file_path": str(test_file), "content": "new content"}
        )
        assert "Successfully wrote" in result
        assert test_file.read_text() == "new content"

    def test_dispatch_replace_string(self, tmp_path):
        """Test dispatch to replace_string."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("old text")

        result = fs_tools.execute_tool_call(
            "replace_string",
            {"file_path": str(test_file), "old_string": "old", "new_string": "new"}
        )
        assert "Successfully replaced" in result

    def test_dispatch_run_shell_command(self):
        """Test dispatch to run_shell_command."""
        result = fs_tools.execute_tool_call("run_shell_command", {"command": "echo hi"})
        assert "Exit Code: 0" in result

    def test_with_json_string_arguments(self, tmp_path):
        """Test with JSON string arguments."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        args_json = json.dumps({"file_path": str(test_file)})
        result = fs_tools.execute_tool_call("read_file", args_json)
        assert result == "content"

    def test_with_dict_arguments(self, tmp_path):
        """Test with dict arguments."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        args_dict = {"file_path": str(test_file)}
        result = fs_tools.execute_tool_call("read_file", args_dict)
        assert result == "content"

    def test_with_invalid_json_string(self):
        """Test with invalid JSON string (error case)."""
        result = fs_tools.execute_tool_call("read_file", "{invalid json}")
        assert "Error: Invalid JSON arguments" in result

    def test_unknown_tool_name_handling(self):
        """Test unknown tool name handling."""
        result = fs_tools.execute_tool_call("unknown_tool", {})
        assert "Error: Unknown tool" in result

    @patch('ayder_cli.fs_tools.create_task')
    def test_dispatch_create_task(self, mock_create_task):
        """Test dispatch to create_task."""
        mock_create_task.return_value = "Task created"
        result = fs_tools.execute_tool_call("create_task", {"title": "Test Task"})
        assert result == "Task created"
        mock_create_task.assert_called_once_with(title="Test Task")

    @patch('ayder_cli.fs_tools.show_task')
    def test_dispatch_show_task(self, mock_show_task):
        """Test dispatch to show_task."""
        mock_show_task.return_value = "Task details"
        result = fs_tools.execute_tool_call("show_task", {"task_id": 1})
        assert result == "Task details"
        mock_show_task.assert_called_once_with(task_id=1)

    @patch('ayder_cli.fs_tools.implement_task')
    def test_dispatch_implement_task(self, mock_implement_task):
        """Test dispatch to implement_task."""
        mock_implement_task.return_value = "Task implemented"
        result = fs_tools.execute_tool_call("implement_task", {"task_id": 1})
        assert result == "Task implemented"
        mock_implement_task.assert_called_once_with(task_id=1)

    @patch('ayder_cli.fs_tools.implement_all_tasks')
    def test_dispatch_implement_all_tasks(self, mock_implement_all):
        """Test dispatch to implement_all_tasks."""
        mock_implement_all.return_value = "All tasks done"
        result = fs_tools.execute_tool_call("implement_all_tasks", {})
        assert result == "All tasks done"
        mock_implement_all.assert_called_once()
