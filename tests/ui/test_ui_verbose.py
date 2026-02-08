"""Tests for UI verbose LLM request display."""

from unittest.mock import patch
from ayder_cli.ui import print_llm_request_debug


class TestPrintLLMRequestDebug:
    """Test LLM request debug formatter."""

    @patch("ayder_cli.ui.console")
    def test_basic_request_display(self, mock_console):
        """Test basic LLM request display."""
        messages = [
            {"role": "system", "content": "You are an assistant"},
            {"role": "user", "content": "Hello"}
        ]
        tools = [{"function": {"name": "read_file"}}]
        options = {"num_ctx": 8192}
        
        print_llm_request_debug(messages, "qwen3-coder:latest", tools, options)
        
        # Verify console.print was called
        mock_console.print.assert_called_once()
        
        # Get the Panel argument
        panel = mock_console.print.call_args[0][0]
        
        # Check panel properties
        assert "qwen3-coder:latest" in panel.title
        assert "Messages: 2" in panel.subtitle
        assert "Tools: 1" in panel.subtitle
        assert "8192 tokens" in panel.subtitle

    @patch("ayder_cli.ui.console")
    def test_no_tools_display(self, mock_console):
        """Test display when no tools provided."""
        messages = [{"role": "user", "content": "Hello"}]
        
        print_llm_request_debug(messages, "test-model", None, None)
        
        mock_console.print.assert_called_once()
        
        panel = mock_console.print.call_args[0][0]
        assert "Tools: 0" in panel.subtitle
        assert "default" in panel.subtitle  # Default context

    @patch("ayder_cli.ui.console")
    def test_message_truncation(self, mock_console):
        """Test that long messages are truncated."""
        long_content = "a" * 300  # 300 characters
        messages = [{"role": "user", "content": long_content}]
        
        print_llm_request_debug(messages, "test-model", None, None)
        
        mock_console.print.assert_called_once()
        
        # Get the Text content from Panel
        panel = mock_console.print.call_args[0][0]
        content_text = str(panel.renderable)
        
        # Should contain truncation indicator
        assert "..." in content_text

    @patch("ayder_cli.ui.console")
    def test_multiple_tools_display(self, mock_console):
        """Test display with multiple tools."""
        messages = [{"role": "user", "content": "Test"}]
        tools = [
            {"function": {"name": "read_file"}},
            {"function": {"name": "write_file"}},
            {"function": {"name": "list_files"}}
        ]
        
        print_llm_request_debug(messages, "test-model", tools, None)
        
        mock_console.print.assert_called_once()
        
        panel = mock_console.print.call_args[0][0]
        assert "Tools: 3" in panel.subtitle

    @patch("ayder_cli.ui.console")
    def test_empty_messages(self, mock_console):
        """Test with empty messages list."""
        messages = []
        
        print_llm_request_debug(messages, "test-model", None, None)
        
        mock_console.print.assert_called_once()
        
        panel = mock_console.print.call_args[0][0]
        assert "Messages: 0" in panel.subtitle

    @patch("ayder_cli.ui.console")
    def test_newline_replacement(self, mock_console):
        """Test that newlines in messages are replaced with spaces."""
        messages = [{"role": "user", "content": "Line 1\nLine 2\nLine 3"}]
        
        print_llm_request_debug(messages, "test-model", None, None)
        
        mock_console.print.assert_called_once()
        
        # The display should not contain actual newlines in message preview
        panel = mock_console.print.call_args[0][0]
        content_text = str(panel.renderable)
        
        # Should contain the content but newlines replaced
        assert "Line 1" in content_text

    @patch("ayder_cli.ui.console")
    def test_non_string_content(self, mock_console):
        """Test handling of non-string message content."""
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "tool", "content": {"result": "success"}}  # Non-string content
        ]
        
        # Should not raise an error
        print_llm_request_debug(messages, "test-model", None, None)
        
        mock_console.print.assert_called_once()

    @patch("ayder_cli.ui.console")
    def test_message_objects_instead_of_dicts(self, mock_console):
        """Test handling of message objects (not dicts) from OpenAI SDK."""
        # Create mock message objects
        class MockMessage:
            def __init__(self, role, content):
                self.role = role
                self.content = content
        
        messages = [
            MockMessage("system", "You are an assistant"),
            MockMessage("user", "Hello")
        ]
        
        # Should not raise an error
        print_llm_request_debug(messages, "test-model", None, None)
        
        mock_console.print.assert_called_once()
        panel = mock_console.print.call_args[0][0]
        assert "Messages: 2" in panel.subtitle

    @patch("ayder_cli.ui.console")
    def test_options_as_object(self, mock_console):
        """Test handling of options as object instead of dict."""
        messages = [{"role": "user", "content": "Test"}]
        
        # Options might not be a dict
        class MockOptions:
            pass
        
        options = MockOptions()
        
        # Should not raise an error
        print_llm_request_debug(messages, "test-model", None, options)
        
        mock_console.print.assert_called_once()
        panel = mock_console.print.call_args[0][0]
        assert "default" in panel.subtitle  # Should fall back to "default"

