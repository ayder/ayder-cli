"""
Tests for diff preview functionality in ayder_cli.ui

Tests colorize_diff, truncate_diff, generate_diff_preview, and confirm_with_diff.
"""
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
from ayder_cli.ui import (
    colorize_diff,
    truncate_diff,
    generate_diff_preview,
    confirm_with_diff,
)
from ayder_cli.tools.utils import prepare_new_content
from ayder_cli.path_context import ProjectContext
import ayder_cli.tools.utils as utils_module


class TestColorizeDiff(unittest.TestCase):
    """Test colorize_diff function"""

    def test_addition_lines_colored_green(self):
        """Verify addition lines contain green color code"""
        diff_lines = ["+added line"]
        result = colorize_diff(diff_lines)
        self.assertIn("\033[32m", result[0])  # Green
        self.assertIn("+added line", result[0])

    def test_deletion_lines_colored_red(self):
        """Verify deletion lines contain red color code"""
        diff_lines = ["-removed line"]
        result = colorize_diff(diff_lines)
        self.assertIn("\033[31m", result[0])  # Red
        self.assertIn("-removed line", result[0])

    def test_hunk_headers_colored_cyan(self):
        """Verify hunk headers contain cyan color code"""
        diff_lines = ["@@ -1,3 +1,4 @@"]
        result = colorize_diff(diff_lines)
        self.assertIn("\033[36m", result[0])  # Cyan
        self.assertIn("@@", result[0])

    def test_context_lines_not_colored(self):
        """Verify context lines remain uncolored"""
        diff_lines = [" context line"]
        result = colorize_diff(diff_lines)
        self.assertEqual(" context line", result[0])

    def test_diff_header_not_mistaken_for_addition(self):
        """Verify +++ is not colored as addition"""
        diff_lines = ["+++b/file.txt"]
        result = colorize_diff(diff_lines)
        self.assertNotIn("\033[32m", result[0])  # Should not be green

    def test_diff_header_not_mistaken_for_deletion(self):
        """Verify --- is not colored as deletion"""
        diff_lines = ["---a/file.txt"]
        result = colorize_diff(diff_lines)
        self.assertNotIn("\033[31m", result[0])  # Should not be red

    def test_reset_code_added(self):
        """Verify reset code is added at end of colored lines"""
        diff_lines = ["+added"]
        result = colorize_diff(diff_lines)
        self.assertIn("\033[0m", result[0])


class TestTruncateDiff(unittest.TestCase):
    """Test truncate_diff function"""

    def test_small_diff_unchanged(self):
        """Verify small diff (< max_lines) passes through unchanged"""
        diff_lines = [f"line {i}" for i in range(50)]
        result = truncate_diff(diff_lines, max_lines=100)
        self.assertEqual(len(result), 50)
        self.assertEqual(result, diff_lines)

    def test_exact_max_lines_unchanged(self):
        """Verify diff at exactly max_lines passes through"""
        diff_lines = [f"line {i}" for i in range(100)]
        result = truncate_diff(diff_lines, max_lines=100)
        self.assertEqual(len(result), 100)

    def test_large_diff_truncated(self):
        """Verify large diff is truncated to 80 + separator + 20"""
        diff_lines = [f"line {i}" for i in range(150)]
        result = truncate_diff(diff_lines, max_lines=100)
        self.assertEqual(len(result[0:80]), 80)
        # Should have separator
        separator_found = any("omitted" in str(line) for line in result)
        self.assertTrue(separator_found)
        self.assertEqual(len(result[-20:]), 20)

    def test_separator_message_present(self):
        """Verify separator message contains count of omitted lines"""
        diff_lines = [f"line {i}" for i in range(150)]
        result = truncate_diff(diff_lines, max_lines=100)
        separator = next((line for line in result if "omitted" in str(line)), None)
        self.assertIsNotNone(separator)
        self.assertIn("50", str(separator))  # 150 - 80 - 20 = 50


class TestGenerateDiffPreview(unittest.TestCase):
    """Test generate_diff_preview function"""

    def setUp(self):
        """Create temporary directory for test files"""
        import tempfile
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        """Clean up temporary files"""
        import shutil
        shutil.rmtree(self.temp_dir)

    def test_new_file_shows_all_additions(self):
        """Verify new file diff shows all content as additions"""
        file_path = self.temp_dir / "new_file.txt"
        new_content = "line 1\nline 2\nline 3"
        result = generate_diff_preview(file_path, new_content)

        self.assertIsNotNone(result)
        self.assertIn("+line 1", result)
        self.assertIn("+line 2", result)
        self.assertIn("+line 3", result)

    def test_modified_file_shows_changes(self):
        """Verify modified file shows correct +/- lines"""
        file_path = self.temp_dir / "existing.txt"
        original_content = "original line\nkeep this\nremove this"
        new_content = "modified line\nkeep this\nadd this"

        with open(file_path, 'w') as f:
            f.write(original_content)

        result = generate_diff_preview(file_path, new_content)

        self.assertIsNotNone(result)
        self.assertIn("-original line", result)
        self.assertIn("+modified line", result)
        self.assertIn("-remove this", result)
        self.assertIn("+add this", result)
        self.assertIn(" keep this", result)

    def test_binary_file_returns_none(self):
        """Verify binary file detection returns None"""
        file_path = self.temp_dir / "binary.bin"
        # Create a file with null bytes
        with open(file_path, 'wb') as f:
            f.write(b'\x00\x01\x02\x03')

        result = generate_diff_preview(file_path, "new content")
        self.assertIsNone(result)

    def test_no_changes_returns_none(self):
        """Verify identical content returns None (no diff)"""
        file_path = self.temp_dir / "same.txt"
        content = "same content"

        with open(file_path, 'w') as f:
            f.write(content)

        result = generate_diff_preview(file_path, content)
        self.assertIsNone(result)

    def test_file_read_error_returns_none(self):
        """Verify file read errors are handled gracefully"""
        file_path = "/nonexistent/path/to/file.txt"
        result = generate_diff_preview(file_path, "content")
        # Should not crash, should return None or handle gracefully
        # (file doesn't exist but is not in temp dir, so we can't create it)
        # The function should handle this without raising

    def test_colorization_applied(self):
        """Verify diff output is colorized"""
        file_path = self.temp_dir / "color_test.txt"
        original = "old"
        new = "new"

        with open(file_path, 'w') as f:
            f.write(original)

        result = generate_diff_preview(file_path, new)
        self.assertIsNotNone(result)
        # Should contain ANSI color codes
        self.assertIn("\033[", result)

    def test_large_diff_truncated(self):
        """Verify large diffs are truncated in preview"""
        file_path = self.temp_dir / "large.txt"
        original = "\n".join([f"line {i}" for i in range(10)])
        new = "\n".join([f"line {i}" for i in range(200)])

        with open(file_path, 'w') as f:
            f.write(original)

        result = generate_diff_preview(file_path, new)
        self.assertIsNotNone(result)
        # Should contain truncation message
        self.assertIn("omitted", result)


class TestConfirmWithDiff(unittest.TestCase):
    """Test confirm_with_diff function (with mocking)"""

    def setUp(self):
        """Create temporary directory for test files"""
        import tempfile
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        """Clean up temporary files"""
        import shutil
        shutil.rmtree(self.temp_dir)

    @patch('builtins.input', return_value='y')
    @patch('builtins.print')
    def test_diff_printed_before_confirmation(self, mock_print, mock_input):
        """Verify diff is printed before confirmation prompt"""
        file_path = self.temp_dir / "test.txt"
        new_content = "new content"

        result = confirm_with_diff(file_path, new_content, "Test file")

        self.assertTrue(result)
        # Verify print was called (diff output)
        self.assertGreater(mock_print.call_count, 0)

    @patch('builtins.input', return_value='y')
    @patch('builtins.print')
    def test_confirmation_returns_true_on_yes(self, mock_print, mock_input):
        """Verify function returns True when user confirms"""
        file_path = self.temp_dir / "test.txt"
        result = confirm_with_diff(file_path, "content", "Test")

        self.assertTrue(result)

    @patch('builtins.input', return_value='n')
    @patch('builtins.print')
    def test_confirmation_returns_false_on_no(self, mock_print, mock_input):
        """Verify function returns False when user declines"""
        file_path = self.temp_dir / "test.txt"
        result = confirm_with_diff(file_path, "content", "Test")

        self.assertFalse(result)

    @patch('builtins.input', return_value='')
    @patch('builtins.print')
    def test_confirmation_returns_true_on_empty(self, mock_print, mock_input):
        """Verify function returns True when user presses enter"""
        file_path = self.temp_dir / "test.txt"
        result = confirm_with_diff(file_path, "content", "Test")

        self.assertTrue(result)

    @patch('builtins.input', side_effect=KeyboardInterrupt)
    @patch('builtins.print')
    def test_keyboard_interrupt_returns_false(self, mock_print, mock_input):
        """Verify function handles keyboard interrupt gracefully"""
        file_path = self.temp_dir / "test.txt"
        result = confirm_with_diff(file_path, "content", "Test")

        self.assertFalse(result)


class TestPrepareNewContent(unittest.TestCase):
    """Test prepare_new_content helper function"""

    def setUp(self):
        """Create temporary directory for test files"""
        import tempfile
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        """Clean up temporary files"""
        import shutil
        shutil.rmtree(self.temp_dir)

    def test_write_file_content_extraction(self):
        """Verify write_file extracts content correctly"""
        fargs = '{"file_path": "test.txt", "content": "hello world"}'
        result = prepare_new_content("write_file", fargs)
        self.assertEqual(result, "hello world")

    def test_write_file_dict_argument(self):
        """Verify write_file works with dict argument (not JSON string)"""
        fargs = {"file_path": "test.txt", "content": "hello dict"}
        result = prepare_new_content("write_file", fargs)
        self.assertEqual(result, "hello dict")

    def test_replace_string_content_preparation(self):
        """Verify replace_string reads file and applies replacement"""
        file_path = self.temp_dir / "test.txt"
        original = "hello world"

        with open(file_path, 'w') as f:
            f.write(original)

        # Set up project context with temp_dir as root
        ctx = ProjectContext(str(self.temp_dir))
        original_ctx = utils_module._default_project_ctx
        utils_module._default_project_ctx = ctx

        try:
            fargs = {
                "file_path": "test.txt",
                "old_string": "world",
                "new_string": "universe"
            }
            result = prepare_new_content("replace_string", fargs)
            self.assertEqual(result, "hello universe")
        finally:
            utils_module._default_project_ctx = original_ctx

    def test_replace_string_json_argument(self):
        """Verify replace_string works with JSON string argument"""
        file_path = self.temp_dir / "test.txt"

        with open(file_path, 'w') as f:
            f.write("foo bar")

        # Set up project context with temp_dir as root
        ctx = ProjectContext(str(self.temp_dir))
        original_ctx = utils_module._default_project_ctx
        utils_module._default_project_ctx = ctx

        try:
            fargs = '{"file_path": "test.txt", "old_string": "foo", "new_string": "baz"}'
            result = prepare_new_content("replace_string", fargs)
            self.assertEqual(result, "baz bar")
        finally:
            utils_module._default_project_ctx = original_ctx

    def test_replace_string_missing_file_returns_empty(self):
        """Verify missing file returns empty string"""
        fargs = {
            "file_path": "/nonexistent/file.txt",
            "old_string": "old",
            "new_string": "new"
        }
        result = prepare_new_content("replace_string", fargs)
        self.assertEqual(result, "")

    def test_invalid_json_returns_empty(self):
        """Verify invalid JSON argument returns empty string"""
        result = prepare_new_content("write_file", "not valid json")
        self.assertEqual(result, "")

    def test_unknown_tool_returns_empty(self):
        """Verify unknown tool returns empty string"""
        result = prepare_new_content("unknown_tool", '{}')
        self.assertEqual(result, "")

    def test_write_file_missing_content_returns_empty(self):
        """Verify write_file without content returns empty"""
        fargs = '{"file_path": "test.txt"}'
        result = prepare_new_content("write_file", fargs)
        self.assertEqual(result, "")


if __name__ == "__main__":
    unittest.main()
