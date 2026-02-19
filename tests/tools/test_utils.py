"""Tests for tools/utils.py module.

This module tests the utility functions including:
- Line 30: Returns empty string when file_path is empty
- prepare_new_content for write_file and replace_string
"""

import json
from unittest.mock import patch

import pytest

from ayder_cli.tools.utils import prepare_new_content
from ayder_cli.core.context import ProjectContext


@pytest.fixture
def project_context(tmp_path):
    """Create a project context with tmp_path as root."""
    return ProjectContext(str(tmp_path))


class TestPrepareNewContentWriteFile:
    """Tests for prepare_new_content with write_file."""

    def test_write_file_with_dict_args(self):
        """Test prepare_new_content for write_file with dict args."""
        args = {"content": "Hello, World!"}
        result = prepare_new_content("write_file", args)
        assert result == "Hello, World!"

    def test_write_file_with_json_string_args(self):
        """Test prepare_new_content for write_file with JSON string args."""
        args = json.dumps({"content": "JSON content"})
        result = prepare_new_content("write_file", args)
        assert result == "JSON content"

    def test_write_file_missing_content(self):
        """Test prepare_new_content for write_file with missing content key."""
        args = {"file_path": "/tmp/test.txt"}
        result = prepare_new_content("write_file", args)
        assert result == ""

    def test_write_file_empty_content(self):
        """Test prepare_new_content for write_file with empty content."""
        args = {"content": ""}
        result = prepare_new_content("write_file", args)
        assert result == ""


class TestPrepareNewContentReplaceString:
    """Tests for prepare_new_content with replace_string."""

    def test_replace_string_basic(self, tmp_path, project_context):
        """Test prepare_new_content for replace_string basic case."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")

        args = {
            "file_path": str(test_file),
            "old_string": "World",
            "new_string": "Universe"
        }
        result = prepare_new_content("replace_string", args, project_context)
        assert result == "Hello, Universe!"

    def test_replace_string_with_json_args(self, tmp_path, project_context):
        """Test prepare_new_content for replace_string with JSON string args."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Original text")

        args = json.dumps({
            "file_path": str(test_file),
            "old_string": "Original",
            "new_string": "Modified"
        })
        result = prepare_new_content("replace_string", args, project_context)
        assert result == "Modified text"

    def test_replace_string_empty_file_path(self):
        """Test prepare_new_content returns empty when file_path is empty - Line 30."""
        args = {
            "file_path": "",
            "old_string": "old",
            "new_string": "new"
        }
        result = prepare_new_content("replace_string", args)
        assert result == ""

    def test_replace_string_missing_file_path(self):
        """Test prepare_new_content returns empty when file_path is missing."""
        args = {
            "old_string": "old",
            "new_string": "new"
        }
        result = prepare_new_content("replace_string", args)
        assert result == ""

    def test_replace_string_file_not_found(self):
        """Test prepare_new_content returns empty when file doesn't exist."""
        args = {
            "file_path": "/nonexistent/file/path.txt",
            "old_string": "old",
            "new_string": "new"
        }
        result = prepare_new_content("replace_string", args)
        assert result == ""

    def test_replace_string_multiple_occurrences(self, tmp_path, project_context):
        """Test replace_string with multiple occurrences of old_string."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("old old old text")

        args = {
            "file_path": str(test_file),
            "old_string": "old",
            "new_string": "new"
        }
        result = prepare_new_content("replace_string", args, project_context)
        assert result == "new new new text"

    def test_replace_string_no_match(self, tmp_path, project_context):
        """Test replace_string when old_string is not found."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Some content")

        args = {
            "file_path": str(test_file),
            "old_string": "notfound",
            "new_string": "replacement"
        }
        result = prepare_new_content("replace_string", args, project_context)
        # Should return original content unchanged
        assert result == "Some content"

    def test_replace_string_empty_old_string(self, tmp_path, project_context):
        """Test replace_string with empty old_string."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("ABC")

        args = {
            "file_path": str(test_file),
            "old_string": "",
            "new_string": "X"
        }
        result = prepare_new_content("replace_string", args, project_context)
        # Empty string replacement behavior
        assert "X" in result

    def test_replace_string_multiline_content(self, tmp_path, project_context):
        """Test replace_string with multiline content."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Line 1\nLine 2\nLine 3")

        args = {
            "file_path": str(test_file),
            "old_string": "Line 2",
            "new_string": "Modified Line"
        }
        result = prepare_new_content("replace_string", args, project_context)
        assert result == "Line 1\nModified Line\nLine 3"


class TestPrepareNewContentEdgeCases:
    """Edge case tests for prepare_new_content."""

    def test_unknown_function_name(self):
        """Test prepare_new_content with unknown function name."""
        args = {"content": "test"}
        result = prepare_new_content("unknown_function", args)
        assert result == ""

    def test_invalid_json_string(self):
        """Test prepare_new_content with invalid JSON string."""
        args = "not valid json {"
        result = prepare_new_content("write_file", args)
        assert result == ""

    def test_empty_args_dict(self):
        """Test prepare_new_content with empty args dict."""
        result = prepare_new_content("write_file", {})
        assert result == ""

    def test_none_args(self):
        """Test prepare_new_content with None args."""
        result = prepare_new_content("write_file", None)
        assert result == ""

    @patch("ayder_cli.tools.utils.open", side_effect=PermissionError("Permission denied"))
    def test_replace_string_permission_error(self, mock_file):
        """Test replace_string handles permission error."""
        args = {
            "file_path": "/restricted/file.txt",
            "old_string": "old",
            "new_string": "new"
        }
        result = prepare_new_content("replace_string", args)
        assert result == ""

    @patch("ayder_cli.tools.utils.open", side_effect=IOError("IO error"))
    def test_replace_string_io_error(self, mock_file):
        """Test replace_string handles IO error."""
        args = {
            "file_path": "/some/file.txt",
            "old_string": "old",
            "new_string": "new"
        }
        result = prepare_new_content("replace_string", args)
        assert result == ""
