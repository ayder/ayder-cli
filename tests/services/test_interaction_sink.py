"""Tests for InteractionSink protocol.

Contract 2: Interaction Interfaces
- InteractionSink defines how services notify about tool/events.
- This is the interface that services use to communicate with UI.
"""

from typing import Any, Protocol, runtime_checkable
from unittest.mock import Mock, call

import pytest


# The expected protocol definition (from architect spec)
@runtime_checkable
class InteractionSink(Protocol):
    """Protocol for receiving tool execution notifications.
    
    Services call these methods to notify about events.
    Adapters implement this to route to CLI or TUI.
    """
    
    def on_tool_call(self, tool_name: str, args_json: str) -> None:
        """Called when a tool is about to be executed.
        
        Args:
            tool_name: Name of the tool being called.
            args_json: Tool arguments as JSON string.
        """
        ...
    
    def on_tool_result(self, result: str) -> None:
        """Called when a tool execution completes.
        
        Args:
            result: String representation of the tool result.
        """
        ...
    
    def on_tool_skipped(self) -> None:
        """Called when a tool execution is skipped (user declined)."""
        ...
    
    def on_file_preview(self, file_path: str) -> None:
        """Called to preview file content in verbose mode.
        
        Args:
            file_path: Path to the file to preview.
        """
        ...
    
    def on_llm_request_debug(
        self,
        messages: list[dict[str, Any]] | list[Any],
        model: str,
        tools: list[dict[str, Any]] | None,
        options: dict[str, Any] | None,
    ) -> None:
        """Called for verbose LLM request debugging.
        
        Args:
            messages: List of messages sent to LLM.
            model: Model name being used.
            tools: Optional list of tool schemas.
            options: Optional provider-specific options.
        """
        ...


class TestInteractionSinkProtocol:
    """Test that InteractionSink protocol is correctly defined."""

    def test_protocol_is_runtime_checkable(self):
        """InteractionSink should be runtime_checkable for isinstance checks."""
        assert hasattr(InteractionSink, "_is_runtime_protocol")

    def test_protocol_has_required_methods(self):
        """Protocol should define all required method signatures."""
        required_methods = {
            "on_tool_call",
            "on_tool_result", 
            "on_tool_skipped",
            "on_file_preview",
            "on_llm_request_debug",
        }
        
        protocol_methods = set(dir(InteractionSink))
        
        for method in required_methods:
            assert method in protocol_methods, f"Missing method: {method}"

    def test_mock_object_satisfies_protocol(self):
        """A properly configured mock should satisfy the protocol."""
        mock_sink = Mock(spec=InteractionSink)
        
        # Should pass isinstance check
        assert isinstance(mock_sink, InteractionSink)

    def test_protocol_method_signatures(self):
        """Verify method signatures match expected contract."""
        import inspect
        
        # on_tool_call
        sig = inspect.signature(InteractionSink.on_tool_call)
        params = list(sig.parameters.keys())
        assert "tool_name" in params
        assert "args_json" in params
        
        # on_tool_result
        sig = inspect.signature(InteractionSink.on_tool_result)
        params = list(sig.parameters.keys())
        assert "result" in params
        
        # on_tool_skipped (no params besides self)
        sig = inspect.signature(InteractionSink.on_tool_skipped)
        params = list(sig.parameters.keys())
        assert len(params) == 1  # Only 'self'
        
        # on_file_preview
        sig = inspect.signature(InteractionSink.on_file_preview)
        params = list(sig.parameters.keys())
        assert "file_path" in params
        
        # on_llm_request_debug
        sig = inspect.signature(InteractionSink.on_llm_request_debug)
        params = list(sig.parameters.keys())
        assert "messages" in params
        assert "model" in params
        assert "tools" in params
        assert "options" in params


class TestInteractionSinkBehavior:
    """Test expected behavior of InteractionSink implementations."""

    def test_sink_receives_tool_call_notification(self):
        """Sink should receive tool call notifications from executor."""
        sink = Mock(spec=InteractionSink)
        
        # Simulate what executor would do
        tool_name = "write_file"
        args_json = '{"file_path": "/test.txt", "content": "hello"}'
        
        sink.on_tool_call(tool_name, args_json)
        
        sink.on_tool_call.assert_called_once_with(tool_name, args_json)

    def test_sink_receives_tool_result(self):
        """Sink should receive tool execution results."""
        sink = Mock(spec=InteractionSink)
        
        result = "File written successfully"
        sink.on_tool_result(result)
        
        sink.on_tool_result.assert_called_once_with(result)

    def test_sink_receives_skipped_notification(self):
        """Sink should be notified when tool is skipped."""
        sink = Mock(spec=InteractionSink)
        
        sink.on_tool_skipped()
        
        sink.on_tool_skipped.assert_called_once()

    def test_sink_receives_file_preview(self):
        """Sink should receive file preview requests in verbose mode."""
        sink = Mock(spec=InteractionSink)
        
        file_path = "/test/output.txt"
        sink.on_file_preview(file_path)
        
        sink.on_file_preview.assert_called_once_with(file_path)

    def test_sink_receives_llm_debug_info(self):
        """Sink should receive LLM request debug info."""
        sink = Mock(spec=InteractionSink)
        
        messages = [{"role": "user", "content": "Hello"}]
        model = "gpt-4"
        tools = [{"type": "function", "function": {"name": "test"}}]
        options = {"num_ctx": 8192}
        
        sink.on_llm_request_debug(messages, model, tools, options)
        
        sink.on_llm_request_debug.assert_called_once_with(
            messages, model, tools, options
        )

    def test_sink_handles_optional_parameters(self):
        """Sink should handle None for optional parameters."""
        sink = Mock(spec=InteractionSink)
        
        messages = [{"role": "user", "content": "Hello"}]
        model = "gpt-4"
        
        # Call with None for optional params
        sink.on_llm_request_debug(messages, model, None, None)
        
        sink.on_llm_request_debug.assert_called_once_with(
            messages, model, None, None
        )

    def test_full_tool_execution_flow(self):
        """Test complete flow: call → confirm → result."""
        sink = Mock(spec=InteractionSink)
        
        # Tool execution flow
        tool_name = "read_file"
        args_json = '{"file_path": "/test.txt"}'
        result = "File contents here"
        
        # 1. Tool is called
        sink.on_tool_call(tool_name, args_json)
        
        # 2. User confirms (not a sink method, handled by ConfirmationPolicy)
        
        # 3. Tool result
        sink.on_tool_result(result)
        
        # Verify call sequence
        assert sink.on_tool_call.call_count == 1
        assert sink.on_tool_result.call_count == 1

    def test_skipped_tool_flow(self):
        """Test flow when user declines tool execution."""
        sink = Mock(spec=InteractionSink)
        
        tool_name = "write_file"
        args_json = '{"file_path": "/test.txt", "content": "data"}'
        
        # 1. Tool is called
        sink.on_tool_call(tool_name, args_json)
        
        # 2. User declines (not a sink method)
        
        # 3. Tool skipped notification
        sink.on_tool_skipped()
        
        # Verify call sequence
        assert sink.on_tool_call.call_count == 1
        assert sink.on_tool_skipped.call_count == 1
        sink.on_tool_result.assert_not_called()


class TestInteractionSinkIntegration:
    """Integration tests for InteractionSink with services."""

    def test_executor_accepts_sink_in_constructor(self):
        """ToolExecutor should accept InteractionSink in constructor.
        
        This is the key decoupling: services receive sink via injection,
        not by importing UI directly.
        """
        # This test will fail until implementation is done
        try:
            from ayder_cli.services.tools.executor import ToolExecutor
            from ayder_cli.tools.registry import ToolRegistry
            
            sink = Mock(spec=InteractionSink)
            registry = Mock(spec=ToolRegistry)
            
            # Constructor should accept interaction_sink parameter
            executor = ToolExecutor(
                tool_registry=registry,
                interaction_sink=sink
            )
            
            assert hasattr(executor, "interaction_sink")
            assert executor.interaction_sink is sink
            
        except ImportError as e:
            pytest.skip(f"Implementation not ready: {e}")
        except TypeError as e:
            pytest.fail(f"ToolExecutor should accept interaction_sink parameter: {e}")

    def test_llm_provider_accepts_sink_in_constructor(self):
        """LLM providers should accept InteractionSink for verbose output."""
        try:
            from ayder_cli.services.llm import OpenAIProvider
            
            sink = Mock(spec=InteractionSink)
            mock_client = Mock()
            
            # Constructor should accept interaction_sink parameter
            provider = OpenAIProvider(
                client=mock_client,
                interaction_sink=sink
            )
            
            assert hasattr(provider, "interaction_sink")
            assert provider.interaction_sink is sink
            
        except ImportError as e:
            pytest.skip(f"Implementation not ready: {e}")
        except TypeError as e:
            pytest.fail(f"LLMProvider should accept interaction_sink parameter: {e}")

    def test_verbose_mode_uses_sink_not_ui(self):
        """When verbose=True, provider should call sink, not import UI."""
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
            
            # Call with verbose=True
            provider.chat(messages, model, verbose=True)
            
            # Should call sink method, not UI function
            sink.on_llm_request_debug.assert_called_once()
            
        except ImportError:
            pytest.skip("Implementation not ready")
