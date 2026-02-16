"""Integration tests for ToolExecutor with injected interfaces.

Contract 3: Executor Integration
- ToolExecutor must use injected InteractionSink and ConfirmationPolicy.
- No direct UI imports allowed.
"""

import json
from typing import Any, Protocol, runtime_checkable
from unittest.mock import Mock, MagicMock, patch

import pytest


# Protocol definitions (mirroring architect spec)
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


@runtime_checkable
class ConfirmationPolicy(Protocol):
    """Protocol for tool execution confirmation."""
    
    def confirm_action(self, description: str) -> bool: ...
    def confirm_file_diff(
        self, file_path: str, new_content: str, description: str
    ) -> bool: ...


class TestToolExecutorInterfaceInjection:
    """Test that ToolExecutor accepts and uses injected interfaces."""

    def test_executor_constructor_accepts_interfaces(self):
        """ToolExecutor constructor should accept sink and policy."""
        try:
            from ayder_cli.services.tools.executor import ToolExecutor
            from ayder_cli.tools.registry import ToolRegistry
            
            registry = Mock(spec=ToolRegistry)
            sink = Mock(spec=InteractionSink)
            policy = Mock(spec=ConfirmationPolicy)
            
            executor = ToolExecutor(
                tool_registry=registry,
                interaction_sink=sink,
                confirmation_policy=policy
            )
            
            assert executor.tool_registry is registry
            assert executor.interaction_sink is sink
            assert executor.confirmation_policy is policy
            
        except ImportError as e:
            pytest.skip(f"Implementation not ready: {e}")
        except TypeError as e:
            pytest.fail(f"Constructor missing interface parameters: {e}")

    def test_executor_stores_interfaces_as_attributes(self):
        """Executor should store interfaces as instance attributes."""
        try:
            from ayder_cli.services.tools.executor import ToolExecutor
            from ayder_cli.tools.registry import ToolRegistry
            
            registry = Mock(spec=ToolRegistry)
            sink = Mock(spec=InteractionSink)
            policy = Mock(spec=ConfirmationPolicy)
            
            executor = ToolExecutor(
                tool_registry=registry,
                interaction_sink=sink,
                confirmation_policy=policy
            )
            
            assert hasattr(executor, "interaction_sink")
            assert hasattr(executor, "confirmation_policy")
            
        except ImportError:
            pytest.skip("Implementation not ready")


class TestToolExecutorExecutionFlow:
    """Test tool execution flow with injected interfaces."""

    def _create_mock_executor(self):
        """Helper to create executor with mocked dependencies."""
        try:
            from ayder_cli.services.tools.executor import ToolExecutor
            from ayder_cli.tools.registry import ToolRegistry
            
            registry = Mock(spec=ToolRegistry)
            sink = Mock(spec=InteractionSink)
            policy = Mock(spec=ConfirmationPolicy)
            
            executor = ToolExecutor(
                tool_registry=registry,
                interaction_sink=sink,
                confirmation_policy=policy
            )
            
            return executor, registry, sink, policy
        except ImportError:
            return None, None, None, None

    def test_execute_notifies_sink_of_tool_call(self):
        """Executor should call sink.on_tool_call before execution."""
        executor, registry, sink, policy = self._create_mock_executor()
        if executor is None:
            pytest.skip("Implementation not ready")
        
        # Setup mocks
        registry.validate_args.return_value = (True, None)
        registry.normalize_args.return_value = {"file_path": "/test.txt"}
        policy.confirm_action.return_value = True
        registry.execute.return_value = Mock(__str__=lambda self: "Success")
        
        # Execute
        result = executor._execute_single_call(
            "read_file",
            {"file_path": "/test.txt"},
            set(),  # No permissions
            False
        )
        
        # Verify sink was notified
        assert sink.on_tool_call.called
        call_args = sink.on_tool_call.call_args
        assert call_args[0][0] == "read_file"

    def test_execute_notifies_sink_of_result(self):
        """Executor should call sink.on_tool_result after execution."""
        executor, registry, sink, policy = self._create_mock_executor()
        if executor is None:
            pytest.skip("Implementation not ready")
        
        registry.validate_args.return_value = (True, None)
        registry.normalize_args.return_value = {"file_path": "/test.txt"}
        policy.confirm_action.return_value = True
        registry.execute.return_value = Mock(__str__=lambda self: "File contents")
        
        executor._execute_single_call(
            "read_file",
            {"file_path": "/test.txt"},
            set(),
            False
        )
        
        # Verify result was sent to sink
        sink.on_tool_result.assert_called_once()

    def test_execute_notifies_sink_when_skipped(self):
        """Executor should call sink.on_tool_skipped when declined."""
        executor, registry, sink, policy = self._create_mock_executor()
        if executor is None:
            pytest.skip("Implementation not ready")
        
        registry.validate_args.return_value = (True, None)
        registry.normalize_args.return_value = {"file_path": "/test.txt"}
        policy.confirm_action.return_value = False  # User declines
        
        result = executor._execute_single_call(
            "read_file",
            {"file_path": "/test.txt"},
            set(),
            False
        )
        
        # Verify skipped was called
        sink.on_tool_skipped.assert_called_once()
        # Result should not be called
        sink.on_tool_result.assert_not_called()

    def test_confirmation_uses_policy(self):
        """Executor should use injected policy for confirmation."""
        executor, registry, sink, policy = self._create_mock_executor()
        if executor is None:
            pytest.skip("Implementation not ready")
        
        registry.validate_args.return_value = (True, None)
        registry.normalize_args.return_value = {"file_path": "/test.txt"}
        policy.confirm_action.return_value = True
        registry.execute.return_value = Mock(__str__=lambda self: "Success")
        
        executor._execute_single_call(
            "read_file",
            {"file_path": "/test.txt"},
            set(),
            False
        )
        
        # Verify policy was consulted
        policy.confirm_action.assert_called_once()

    def test_write_tool_uses_confirm_file_diff(self):
        """Write operations should use policy.confirm_file_diff."""
        executor, registry, sink, policy = self._create_mock_executor()
        if executor is None:
            pytest.skip("Implementation not ready")
        
        registry.validate_args.return_value = (True, None)
        registry.normalize_args.return_value = {
            "file_path": "/test.txt",
            "content": "hello"
        }
        policy.confirm_file_diff.return_value = True
        registry.execute.return_value = Mock(__str__=lambda self: "Success")
        
        executor._execute_single_call(
            "write_file",
            {"file_path": "/test.txt", "content": "hello"},
            set(),
            False
        )
        
        # Verify confirm_file_diff was called
        policy.confirm_file_diff.assert_called_once()

    def test_auto_approved_skips_confirmation(self):
        """Tools with granted permission should skip policy calls.
        
        Tests public behavior: when permission is in granted_permissions,
        confirmation_policy should NOT be called, but tool should still execute.
        """
        executor, registry, sink, policy = self._create_mock_executor()
        if executor is None:
            pytest.skip("Implementation not ready")
        
        registry.validate_args.return_value = (True, None)
        registry.normalize_args.return_value = {"file_path": "/test.txt"}
        registry.execute.return_value = Mock(__str__=lambda self: "Success")
        
        # Execute with 'r' permission in granted_permissions
        executor._execute_single_call(
            "read_file",
            {"file_path": "/test.txt"},
            {"r"},  # Permission 'r' is granted - should auto-approve
            False
        )
        
        # Policy should NOT be called for auto-approved tools
        policy.confirm_action.assert_not_called()
        policy.confirm_file_diff.assert_not_called()
        
        # But tool should still execute
        registry.execute.assert_called_once()
        
        # And sink should still receive notifications
        sink.on_tool_call.assert_called_once()
        sink.on_tool_result.assert_called_once()

    def test_verbose_mode_triggers_file_preview(self):
        """In verbose mode, write_file should trigger file preview."""
        from unittest.mock import patch
        executor, registry, sink, policy = self._create_mock_executor()
        if executor is None:
            pytest.skip("Implementation not ready")

        registry.normalize_args.return_value = {
            "file_path": "/test/output.txt",
            "content": "data"
        }
        policy.confirm_file_diff.return_value = True

        from ayder_cli.application.execution_policy import ExecutionResult
        fake_result = ExecutionResult(success=True, result="File written")

        with patch(
            "ayder_cli.application.execution_policy.ExecutionPolicy.execute_with_registry",
            return_value=fake_result,
        ):
            executor._execute_single_call(
                "write_file",
                {"file_path": "/test/output.txt", "content": "data"},
                {"w"},
                verbose=True,
            )

        # Verify file preview was triggered
        sink.on_file_preview.assert_called_once_with("/test/output.txt")


class TestToolExecutorNoDirectUI:
    """Test that ToolExecutor does not call UI functions directly."""

    def test_no_direct_print_tool_call(self):
        """Executor should not call print_tool_call directly."""
        # This test verifies the architecture - no direct UI calls
        # The implementation should use sink.on_tool_call instead
        try:
            from ayder_cli.services.tools import executor as executor_module
            
            # Check that print_tool_call is not called in _execute_single_call
            source = executor_module.__file__
            import inspect
            
            # Get source of _execute_single_call
            executor_class = getattr(executor_module, "ToolExecutor", None)
            if executor_class:
                method = getattr(executor_class, "_execute_single_call", None)
                if method:
                    source_code = inspect.getsource(method)
                    assert "print_tool_call(" not in source_code, (
                        "Use sink.on_tool_call instead of print_tool_call"
                    )
        except ImportError:
            pytest.skip("Implementation not ready")

    def test_no_direct_confirm_tool_call(self):
        """Executor should not call confirm_tool_call directly."""
        try:
            from ayder_cli.services.tools import executor as executor_module
            import inspect
            
            executor_class = getattr(executor_module, "ToolExecutor", None)
            if executor_class:
                method = getattr(executor_class, "_execute_single_call", None)
                if method:
                    source_code = inspect.getsource(method)
                    assert "confirm_tool_call(" not in source_code, (
                        "Use policy.confirm_action instead of confirm_tool_call"
                    )
        except ImportError:
            pytest.skip("Implementation not ready")

    def test_no_direct_ui_imports(self):
        """Verify no ayder_cli.ui imports in executor module."""
        try:
            from ayder_cli.services.tools import executor as executor_module
            import ast
            
            source_path = executor_module.__file__
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
            
            assert not ui_imports, (
                f"Executor should not import from ayder_cli.ui: {ui_imports}"
            )
        except ImportError:
            pytest.skip("Implementation not ready")


class TestToolExecutorEdgeCases:
    """Test edge cases in executor behavior."""

    def test_executor_handles_validation_error(self):
        """Executor should handle validation errors gracefully."""
        try:
            from ayder_cli.services.tools.executor import ToolExecutor
            from ayder_cli.tools.registry import ToolRegistry

            registry = Mock(spec=ToolRegistry)
            sink = Mock(spec=InteractionSink)
            policy = Mock(spec=ConfirmationPolicy)

            registry.normalize_args.return_value = {"bad": "args"}

            executor = ToolExecutor(
                tool_registry=registry,
                interaction_sink=sink,
                confirmation_policy=policy
            )

            # "invalid_tool" is not in _KNOWN_TOOLS — ValidationAuthority returns error
            result = executor._execute_single_call(
                "invalid_tool",
                {"bad": "args"},
                {"r", "w", "x"},
                False
            )

            # Result should indicate error
            assert result[0] == "error"
            
        except ImportError:
            pytest.skip("Implementation not ready")

    def test_executor_handles_normalization_error(self):
        """Executor should handle argument normalization errors."""
        try:
            from ayder_cli.services.tools.executor import ToolExecutor
            from ayder_cli.tools.registry import ToolRegistry
            
            registry = Mock(spec=ToolRegistry)
            sink = Mock(spec=InteractionSink)
            policy = Mock(spec=ConfirmationPolicy)
            
            registry.normalize_args.side_effect = ValueError("Bad args")
            
            executor = ToolExecutor(
                tool_registry=registry,
                interaction_sink=sink,
                confirmation_policy=policy
            )
            
            result = executor._execute_single_call(
                "some_tool",
                {"bad": "args"},
                set(),
                False
            )
            
            assert result[0] == "error"
            
        except ImportError:
            pytest.skip("Implementation not ready")
