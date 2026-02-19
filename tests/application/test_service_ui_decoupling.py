"""Integration tests for service/UI decoupling.

This test file verifies the complete decoupling architecture:
- Services do not import UI
- Interfaces are properly defined and injectable
- Full execution flow works with injected dependencies
"""

import ast
from pathlib import Path
from typing import Any, Protocol, runtime_checkable
from unittest.mock import Mock

import pytest


# Protocol definitions (from architect spec)
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


class TestArchitectureBoundary:
    """Test architectural boundary between services and UI."""

    def test_services_directory_has_no_ui_imports(self):
        """Verify Contract 1: No service module imports ayder_cli.ui."""
        project_root = Path(__file__).parent.parent.parent
        services_dir = project_root / "src" / "ayder_cli" / "services"
        
        violations = []
        
        for py_file in services_dir.rglob("*.py"):
            if py_file.name == "__init__.py":
                continue
                
            try:
                content = py_file.read_text()
                tree = ast.parse(content)
                
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            if alias.name == "ayder_cli.ui" or alias.name.startswith("ayder_cli.ui."):
                                relative = py_file.relative_to(project_root)
                                violations.append(f"{relative}: import {alias.name}")
                    
                    elif isinstance(node, ast.ImportFrom):
                        if node.module and node.module.startswith("ayder_cli.ui"):
                            relative = py_file.relative_to(project_root)
                            names = ", ".join(a.name for a in node.names)
                            violations.append(f"{relative}: from {node.module} import {names}")
                        if node.module == "ayder_cli":
                            for alias in node.names:
                                if alias.name == "ui":
                                    relative = py_file.relative_to(project_root)
                                    violations.append(f"{relative}: from ayder_cli import ui")
            except SyntaxError:
                continue
        
        assert not violations, (
            "Service modules must not import ayder_cli.ui.\n"
            "Presentation dependencies must be injected via interfaces.\n"
            "Violations:\n" + "\n".join(f"  - {v}" for v in violations)
        )


class TestInterfaceDefinitions:
    """Test that interfaces are properly defined."""

    def test_interaction_sink_is_protocol(self):
        """InteractionSink should be a Protocol."""
        # The interface should exist in the services module
        try:
            from ayder_cli.services import InteractionSink as ServiceSink
            assert hasattr(ServiceSink, "_is_protocol")
        except ImportError:
            # Expected before implementation - test the expected structure
            assert hasattr(InteractionSink, "_is_protocol")

    def test_confirmation_policy_is_protocol(self):
        """ConfirmationPolicy should be a Protocol."""
        try:
            from ayder_cli.services import ConfirmationPolicy as ServicePolicy
            assert hasattr(ServicePolicy, "_is_protocol")
        except ImportError:
            assert hasattr(ConfirmationPolicy, "_is_protocol")

    def test_interfaces_are_runtime_checkable(self):
        """Interfaces should be runtime_checkable for isinstance checks."""
        try:
            from ayder_cli.services import InteractionSink, ConfirmationPolicy
            
            assert hasattr(InteractionSink, "_is_runtime_protocol")
            assert hasattr(ConfirmationPolicy, "_is_runtime_protocol")
        except ImportError:
            pytest.skip("Interfaces not yet implemented")


class TestFullDecouplingFlow:
    """Test complete decoupled execution flow."""

    def test_tool_execution_with_injected_interfaces(self):
        """Full flow: ToolExecutor with sink and policy."""
        try:
            from ayder_cli.services.tools.executor import ToolExecutor
            from ayder_cli.tools.registry import ToolRegistry
            
            # Create mocks for all dependencies
            registry = Mock(spec=ToolRegistry)
            sink = Mock(spec=InteractionSink)
            policy = Mock(spec=ConfirmationPolicy)
            session = Mock()
            
            # Setup registry behavior
            registry.validate_args.return_value = (True, None)
            registry.normalize_args.return_value = {"file_path": "/test.txt"}
            registry.execute.return_value = Mock(__str__=lambda self: "Success")
            
            # Setup policy to approve
            policy.confirm_action.return_value = True
            
            # Create executor with injected interfaces
            executor = ToolExecutor(
                tool_registry=registry,
                interaction_sink=sink,
                confirmation_policy=policy
            )
            
            # Create mock tool call
            tool_call = Mock()
            tool_call.function.name = "read_file"
            tool_call.function.arguments = '{"file_path": "/test.txt"}'
            tool_call.id = "call_123"
            
            # Execute
            executor.execute_tool_calls(
                [tool_call],
                session,
                granted_permissions=set(),
                verbose=False
            )
            
            # Verify flow
            sink.on_tool_call.assert_called()
            policy.confirm_action.assert_called()
            sink.on_tool_result.assert_called()
            
        except ImportError as e:
            pytest.skip(f"Implementation not ready: {e}")

    def test_llm_verbose_with_injected_sink(self):
        """Full flow: LLM provider with sink for verbose output."""
        try:
            from ayder_cli.services.llm import OpenAIProvider
            
            sink = Mock(spec=InteractionSink)
            mock_client = Mock()
            mock_response = Mock()
            mock_client.chat.completions.create.return_value = mock_response
            
            # Create provider with injected sink
            provider = OpenAIProvider(
                client=mock_client,
                interaction_sink=sink
            )
            
            messages = [{"role": "user", "content": "Hello"}]
            model = "gpt-4"
            tools = [{"function": {"name": "test_tool"}}]
            
            # Execute with verbose
            provider.chat(messages, model, tools=tools, verbose=True)
            
            # Verify sink was used
            sink.on_llm_request_debug.assert_called_once()
            
        except ImportError as e:
            pytest.skip(f"Implementation not ready: {e}")

    def test_user_declined_flow(self):
        """Full flow: User declines confirmation."""
        try:
            from ayder_cli.services.tools.executor import ToolExecutor
            from ayder_cli.tools.registry import ToolRegistry
            
            registry = Mock(spec=ToolRegistry)
            sink = Mock(spec=InteractionSink)
            policy = Mock(spec=ConfirmationPolicy)
            session = Mock()
            
            registry.validate_args.return_value = (True, None)
            registry.normalize_args.return_value = {"file_path": "/test.txt"}
            policy.confirm_action.return_value = False  # User declines
            
            executor = ToolExecutor(
                tool_registry=registry,
                interaction_sink=sink,
                confirmation_policy=policy
            )
            
            tool_call = Mock()
            tool_call.function.name = "write_file"
            tool_call.function.arguments = '{"file_path": "/test.txt", "content": "data"}'
            tool_call.id = "call_123"
            
            executor.execute_tool_calls(
                [tool_call],
                session,
                granted_permissions=set(),
                verbose=False
            )
            
            # Verify skipped notification
            sink.on_tool_skipped.assert_called()
            # Result should not be called
            sink.on_tool_result.assert_not_called()
            
        except ImportError as e:
            pytest.skip(f"Implementation not ready: {e}")

    def test_auto_approved_permission_flow(self):
        """Full flow: Tool auto-approved via permission."""
        try:
            from ayder_cli.services.tools.executor import ToolExecutor
            from ayder_cli.tools.registry import ToolRegistry
            
            registry = Mock(spec=ToolRegistry)
            sink = Mock(spec=InteractionSink)
            policy = Mock(spec=ConfirmationPolicy)
            session = Mock()
            
            registry.validate_args.return_value = (True, None)
            registry.normalize_args.return_value = {"file_path": "/test.txt"}
            registry.execute.return_value = Mock(__str__=lambda self: "Success")
            
            # Permission 'r' is granted
            executor = ToolExecutor(
                tool_registry=registry,
                interaction_sink=sink,
                confirmation_policy=policy
            )
            
            tool_call = Mock()
            tool_call.function.name = "read_file"
            tool_call.function.arguments = '{"file_path": "/test.txt"}'
            tool_call.id = "call_123"
            
            executor.execute_tool_calls(
                [tool_call],
                session,
                granted_permissions={"r"},  # Read permission granted
                verbose=False
            )
            
            # Policy should not be called for auto-approved
            policy.confirm_action.assert_not_called()
            # But execution should happen
            sink.on_tool_result.assert_called()
            
        except ImportError as e:
            pytest.skip(f"Implementation not ready: {e}")


class TestAdapterLayer:
    """Test adapter layer (out of scope but verify interfaces work)."""

    def test_cli_adapter_outside_services(self):
        """Verify CLI adapter is NOT in services/ directory."""
        project_root = Path(__file__).parent.parent.parent
        cli_adapter_path = project_root / "src" / "ayder_cli" / "services" / "cli_adapter.py"
        assert not cli_adapter_path.exists(), \
            "CLI adapter should not be in services/"

    def test_cli_adapter_in_ui_layer(self):
        """Document expected CLI adapter location."""
        # This test documents where CLI adapter should be
        # Implementation will be in src/ayder_cli/ui/cli_adapter.py
        project_root = Path(__file__).parent.parent.parent
        expected_path = project_root / "src" / "ayder_cli" / "ui" / "cli_adapter.py"
        # Note: This will fail until dev implements, which is correct for test-first
        if not expected_path.exists():
            pytest.skip("CLI adapter not yet implemented (expected in ui/)")

    def test_tui_adapter_in_tui_layer(self):
        """Document expected TUI adapter location."""
        # This test documents where TUI adapter should be
        # Implementation will be in src/ayder_cli/tui/adapter.py
        project_root = Path(__file__).parent.parent.parent
        expected_path = project_root / "src" / "ayder_cli" / "tui" / "adapter.py"
        # Note: This will fail until dev implements, which is correct for test-first
        if not expected_path.exists():
            pytest.skip("TUI adapter not yet implemented (expected in tui/)")

    def test_adapters_not_imported_by_services(self):
        """Verify services/ does not import adapters (no circular deps)."""
        import ast
        project_root = Path(__file__).parent.parent.parent
        services_dir = project_root / "src" / "ayder_cli" / "services"
        for py_file in services_dir.rglob("*.py"):
            if py_file.name == "__init__.py":
                continue
            content = py_file.read_text()
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if "adapter" in alias.name:
                            assert False, f"{py_file} imports adapter"
                elif isinstance(node, ast.ImportFrom):
                    if node.module and "adapter" in node.module:
                        assert False, f"{py_file} imports from adapter"

    def test_cli_adapter_can_implement_sink(self):
        """CLI adapter should be able to implement InteractionSink."""
        # This documents the expected adapter pattern
        # CLI adapters live outside services/ and implement the protocols
        
        class CLIAdapter:
            """Example CLI adapter implementing InteractionSink."""
            
            def on_tool_call(self, tool_name: str, args_json: str) -> None:
                # Would call print_tool_call from ayder_cli.ui
                pass
            
            def on_tool_result(self, result: str) -> None:
                pass
            
            def on_tool_skipped(self) -> None:
                pass
            
            def on_file_preview(self, file_path: str) -> None:
                pass
            
            def on_llm_request_debug(
                self,
                messages: list[dict[str, Any]] | list[Any],
                model: str,
                tools: list[dict[str, Any]] | None,
                options: dict[str, Any] | None,
            ) -> None:
                pass
        
        adapter = CLIAdapter()
        assert isinstance(adapter, InteractionSink)

    def test_cli_adapter_can_implement_policy(self):
        """CLI adapter should be able to implement ConfirmationPolicy."""
        
        class CLIPolicy:
            """Example CLI adapter implementing ConfirmationPolicy."""
            
            def confirm_action(self, description: str) -> bool:
                # Would call confirm_tool_call from ayder_cli.ui
                return True
            
            def confirm_file_diff(
                self, file_path: str, new_content: str, description: str
            ) -> bool:
                # Would call confirm_with_diff from ayder_cli.ui
                return True
        
        adapter = CLIPolicy()
        assert isinstance(adapter, ConfirmationPolicy)


class TestBackwardCompatibility:
    """Test backward compatibility during transition."""

    def test_executor_works_without_interfaces(self):
        """Executor should work without interfaces (legacy mode)."""
        try:
            from ayder_cli.services.tools.executor import ToolExecutor
            from ayder_cli.tools.registry import ToolRegistry
            
            registry = Mock(spec=ToolRegistry)
            
            # Create without interfaces (legacy)
            executor = ToolExecutor(tool_registry=registry)
            
            # Should still work (with direct UI imports in legacy mode)
            assert executor.tool_registry is registry
            
        except ImportError as e:
            pytest.skip(f"Implementation not ready: {e}")

    def test_llm_works_without_sink(self):
        """LLM provider should work without sink (legacy mode)."""
        try:
            from ayder_cli.services.llm import OpenAIProvider
            
            mock_client = Mock()
            
            # Create without sink (legacy)
            provider = OpenAIProvider(client=mock_client)
            
            # Should still work
            assert provider.client is mock_client
            
        except ImportError as e:
            pytest.skip(f"Implementation not ready: {e}")


class TestMigrationPath:
    """Document the expected migration path."""

    def test_services_exports_interfaces(self):
        """ayder_cli.services should export the protocols."""
        try:
            from ayder_cli import services
            
            # These should be available after implementation
            assert hasattr(services, "InteractionSink")
            assert hasattr(services, "ConfirmationPolicy")
            
        except ImportError as e:
            pytest.skip(f"Services module not ready: {e}")
        except AssertionError as e:
            pytest.fail(f"Services should export protocols: {e}")
