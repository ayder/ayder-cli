"""Tests for LLM provider verbose mode with InteractionSink.

Contract 4: LLM Verbose Integration
- LLM providers route verbose output through InteractionSink.
- No direct UI imports in llm.py.
"""

from typing import Any, Protocol, runtime_checkable
from unittest.mock import Mock, patch

import pytest


# Protocol definition (mirroring architect spec)
@runtime_checkable
class InteractionSink(Protocol):
    """Protocol for receiving tool execution notifications."""
    
    def on_tool_call(self, tool_name: str, args_json: str) -> None: ...
    def on_tool_result(self, result: str) -> None: ...
    def on_tool_skipped(self) -> None: ...
    def on_file_preview(self, file_path: str) -> None: ...
    def on_llm_request_debug(
        self,
        messages: list[dict[str, Any]] | list[Any],
        model: str,
        tools: list[dict[str, Any]] | None,
        options: dict[str, Any] | None,
    ) -> None: ...


class TestLLMVerboseWithSink:
    """Test LLM verbose mode using InteractionSink."""

    def test_provider_accepts_sink_in_constructor(self):
        """LLM provider should accept InteractionSink in constructor."""
        try:
            from ayder_cli.services.llm import OpenAIProvider
            
            sink = Mock(spec=InteractionSink)
            mock_client = Mock()
            
            provider = OpenAIProvider(
                client=mock_client,
                interaction_sink=sink
            )
            
            assert hasattr(provider, "interaction_sink")
            assert provider.interaction_sink is sink
            
        except ImportError as e:
            pytest.skip(f"Implementation not ready: {e}")
        except TypeError as e:
            pytest.fail(f"Provider should accept interaction_sink: {e}")

    def test_verbose_true_calls_sink_method(self):
        """verbose=True should call sink.on_llm_request_debug."""
        try:
            from ayder_cli.services.llm import OpenAIProvider
            
            sink = Mock(spec=InteractionSink)
            mock_client = Mock()
            mock_response = Mock()
            mock_client.chat.completions.create.return_value = mock_response
            
            provider = OpenAIProvider(
                client=mock_client,
                interaction_sink=sink
            )
            
            messages = [{"role": "user", "content": "Hello"}]
            model = "gpt-4"
            tools = [{"function": {"name": "test_tool"}}]
            options = {"num_ctx": 8192}
            
            provider.chat(messages, model, tools=tools, options=options, verbose=True)
            
            # Verify sink method was called
            sink.on_llm_request_debug.assert_called_once_with(
                messages, model, tools, options
            )
            
        except ImportError:
            pytest.skip("Implementation not ready")

    def test_verbose_false_skips_sink_call(self):
        """verbose=False should not call sink."""
        try:
            from ayder_cli.services.llm import OpenAIProvider
            
            sink = Mock(spec=InteractionSink)
            mock_client = Mock()
            mock_response = Mock()
            mock_client.chat.completions.create.return_value = mock_response
            
            provider = OpenAIProvider(
                client=mock_client,
                interaction_sink=sink
            )
            
            messages = [{"role": "user", "content": "Hello"}]
            
            provider.chat(messages, "gpt-4", verbose=False)
            
            # Sink should not be called
            sink.on_llm_request_debug.assert_not_called()
            
        except ImportError:
            pytest.skip("Implementation not ready")

    def test_verbose_default_false(self):
        """verbose should default to False."""
        try:
            from ayder_cli.services.llm import OpenAIProvider
            
            sink = Mock(spec=InteractionSink)
            mock_client = Mock()
            mock_response = Mock()
            mock_client.chat.completions.create.return_value = mock_response
            
            provider = OpenAIProvider(
                client=mock_client,
                interaction_sink=sink
            )
            
            messages = [{"role": "user", "content": "Hello"}]
            
            # Call without verbose parameter
            provider.chat(messages, "gpt-4")
            
            # Sink should not be called (default is False)
            sink.on_llm_request_debug.assert_not_called()
            
        except ImportError:
            pytest.skip("Implementation not ready")

    def test_verbose_with_no_tools(self):
        """verbose=True with no tools should pass None for tools."""
        try:
            from ayder_cli.services.llm import OpenAIProvider
            
            sink = Mock(spec=InteractionSink)
            mock_client = Mock()
            mock_response = Mock()
            mock_client.chat.completions.create.return_value = mock_response
            
            provider = OpenAIProvider(
                client=mock_client,
                interaction_sink=sink
            )
            
            messages = [{"role": "user", "content": "Hello"}]
            model = "gpt-4"
            
            provider.chat(messages, model, verbose=True)
            
            # Should call with None for tools and options
            sink.on_llm_request_debug.assert_called_once_with(
                messages, model, None, None
            )
            
        except ImportError:
            pytest.skip("Implementation not ready")


class TestLLMProvidersAllSupportSink:
    """Test that all LLM providers support InteractionSink."""

    def test_openai_provider_supports_sink(self):
        """OpenAIProvider should support InteractionSink."""
        try:
            from ayder_cli.services.llm import OpenAIProvider
            
            sink = Mock(spec=InteractionSink)
            mock_client = Mock()
            
            provider = OpenAIProvider(
                client=mock_client,
                interaction_sink=sink
            )
            
            # Should store the sink
            assert provider.interaction_sink is sink
            
        except ImportError:
            pytest.skip("Implementation not ready")

    def test_anthropic_provider_supports_sink(self):
        """AnthropicProvider should support InteractionSink."""
        try:
            from ayder_cli.services.llm import AnthropicProvider
            
            sink = Mock(spec=InteractionSink)
            mock_client = Mock()
            
            provider = AnthropicProvider(
                client=mock_client,
                interaction_sink=sink
            )
            
            assert provider.interaction_sink is sink
            
        except ImportError:
            pytest.skip("Implementation not ready")

    def test_gemini_provider_supports_sink(self):
        """GeminiProvider should support InteractionSink."""
        try:
            from ayder_cli.services.llm import GeminiProvider
            
            sink = Mock(spec=InteractionSink)
            mock_client = Mock()
            
            provider = GeminiProvider(
                client=mock_client,
                interaction_sink=sink
            )
            
            assert provider.interaction_sink is sink
            
        except ImportError:
            pytest.skip("Implementation not ready")


class TestLLMNoDirectUI:
    """Test that LLM providers don't import UI directly."""

    def test_no_direct_ui_import_in_llm_module(self):
        """llm.py should not import from ayder_cli.ui."""
        try:
            from ayder_cli.services import llm as llm_module
            import ast
            
            source_path = llm_module.__file__
            with open(source_path) as f:
                tree = ast.parse(f.read())
            
            ui_imports = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if "ayder_cli.ui" in alias.name:
                            ui_imports.append(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module and "ayder_cli.ui" in node.module:
                        ui_imports.append(node.module)
                    # Check for 'from ayder_cli import ui'
                    if node.module == "ayder_cli":
                        for alias in node.names:
                            if alias.name == "ui":
                                ui_imports.append("ayder_cli.ui")
            
            assert not ui_imports, (
                f"LLM module should not import from ayder_cli.ui: {ui_imports}\n"
                f"Use injected InteractionSink instead."
            )
        except ImportError:
            pytest.skip("Implementation not ready")

    def test_no_print_llm_request_debug_import(self):
        """Should not import print_llm_request_debug from ui."""
        try:
            from ayder_cli.services import llm as llm_module
            import ast
            
            source_path = llm_module.__file__
            with open(source_path) as f:
                source = f.read()
            
            assert "print_llm_request_debug" not in source, (
                "Use sink.on_llm_request_debug instead of print_llm_request_debug"
            )
        except ImportError:
            pytest.skip("Implementation not ready")


class TestLLMVerboseEdgeCases:
    """Test edge cases for LLM verbose mode."""

    def test_sink_can_be_none(self):
        """Provider should work with no sink (backward compatibility)."""
        try:
            from ayder_cli.services.llm import OpenAIProvider
            
            mock_client = Mock()
            mock_response = Mock()
            mock_client.chat.completions.create.return_value = mock_response
            
            # No sink provided
            provider = OpenAIProvider(client=mock_client)
            
            messages = [{"role": "user", "content": "Hello"}]
            
            # Should not raise
            provider.chat(messages, "gpt-4", verbose=False)
            
        except ImportError:
            pytest.skip("Implementation not ready")

    def test_sink_method_receives_correct_types(self):
        """sink.on_llm_request_debug should receive correct argument types."""
        try:
            from ayder_cli.services.llm import OpenAIProvider
            
            sink = Mock(spec=InteractionSink)
            mock_client = Mock()
            mock_response = Mock()
            mock_client.chat.completions.create.return_value = mock_response
            
            provider = OpenAIProvider(
                client=mock_client,
                interaction_sink=sink
            )
            
            messages = [{"role": "user", "content": "Hello"}]
            model = "gpt-4"
            tools = [{"type": "function", "function": {"name": "test"}}]
            options = {"num_ctx": 8192}
            
            provider.chat(messages, model, tools=tools, options=options, verbose=True)
            
            # Get call arguments
            call_args = sink.on_llm_request_debug.call_args
            
            # Verify types
            assert isinstance(call_args[0][0], list)  # messages
            assert isinstance(call_args[0][1], str)   # model
            assert isinstance(call_args[0][2], list) or call_args[0][2] is None  # tools
            assert isinstance(call_args[0][3], dict) or call_args[0][3] is None  # options
            
        except ImportError:
            pytest.skip("Implementation not ready")
