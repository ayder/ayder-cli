"""Tests for LLM provider verbose mode."""

from unittest.mock import Mock, patch
from ayder_cli.services.llm import OpenAIProvider


class TestLLMVerboseMode:
    """Test verbose mode in LLM provider."""

    @patch("ayder_cli.ui.print_llm_request_debug")
    def test_verbose_mode_calls_print_function(self, mock_print):
        """Test that verbose=True triggers print_llm_request_debug."""
        mock_client = Mock()
        mock_response = Mock()
        mock_client.chat.completions.create.return_value = mock_response
        
        provider = OpenAIProvider(client=mock_client)
        messages = [{"role": "user", "content": "Hello"}]
        tools = [{"function": {"name": "test_tool"}}]
        options = {"num_ctx": 8192}
        
        provider.chat(messages, "test-model", tools=tools, options=options, verbose=True)
        
        # Verify print function was called with correct arguments
        mock_print.assert_called_once_with(messages, "test-model", tools, options)
        
        # Verify API call still happened
        mock_client.chat.completions.create.assert_called_once()

    @patch("ayder_cli.ui.print_llm_request_debug")
    def test_non_verbose_mode_skips_print(self, mock_print):
        """Test that verbose=False does not trigger print function."""
        mock_client = Mock()
        mock_response = Mock()
        mock_client.chat.completions.create.return_value = mock_response
        
        provider = OpenAIProvider(client=mock_client)
        messages = [{"role": "user", "content": "Hello"}]
        
        provider.chat(messages, "test-model", verbose=False)
        
        # Print function should NOT be called
        mock_print.assert_not_called()
        
        # But API call should still happen
        mock_client.chat.completions.create.assert_called_once()

    @patch("ayder_cli.ui.print_llm_request_debug")
    def test_verbose_default_false(self, mock_print):
        """Test that verbose defaults to False."""
        mock_client = Mock()
        mock_response = Mock()
        mock_client.chat.completions.create.return_value = mock_response
        
        provider = OpenAIProvider(client=mock_client)
        messages = [{"role": "user", "content": "Hello"}]
        
        # Call without verbose parameter
        provider.chat(messages, "test-model")
        
        # Print function should NOT be called (default is False)
        mock_print.assert_not_called()

    @patch("ayder_cli.ui.print_llm_request_debug")
    def test_verbose_with_no_tools(self, mock_print):
        """Test verbose mode with no tools provided."""
        mock_client = Mock()
        mock_response = Mock()
        mock_client.chat.completions.create.return_value = mock_response
        
        provider = OpenAIProvider(client=mock_client)
        messages = [{"role": "user", "content": "Hello"}]
        
        provider.chat(messages, "test-model", verbose=True)
        
        # Verify print function was called with None for tools and options
        mock_print.assert_called_once_with(messages, "test-model", None, None)
