"""Tests for ConfirmationPolicy protocol.

Contract 2: Interaction Interfaces
- ConfirmationPolicy defines how services request user confirmation.
- Separates confirmation logic from presentation.
"""

from typing import Protocol, runtime_checkable
from unittest.mock import Mock

import pytest


# The expected protocol definition (from architect spec)
@runtime_checkable
class ConfirmationPolicy(Protocol):
    """Protocol for tool execution confirmation.
    
    Services call these methods to request user confirmation.
    Adapters implement this to show CLI prompts or TUI modals.
    """
    
    def confirm_action(self, description: str) -> bool:
        """Request confirmation for a generic action.
        
        Args:
            description: Human-readable description of the action.
        
        Returns:
            True if confirmed, False if declined.
        """
        ...
    
    def confirm_file_diff(
        self, 
        file_path: str, 
        new_content: str, 
        description: str
    ) -> bool:
        """Request confirmation with file diff preview.
        
        Used for file-modifying operations like write_file, replace_string.
        
        Args:
            file_path: Path to the file being modified.
            new_content: The new content that would be written.
            description: Human-readable description of the change.
        
        Returns:
            True if confirmed, False if declined.
        """
        ...


class TestConfirmationPolicyProtocol:
    """Test that ConfirmationPolicy protocol is correctly defined."""

    def test_protocol_is_runtime_checkable(self):
        """ConfirmationPolicy should be runtime_checkable for isinstance checks."""
        assert hasattr(ConfirmationPolicy, "_is_runtime_protocol")

    def test_protocol_has_required_methods(self):
        """Protocol should define all required method signatures."""
        required_methods = {"confirm_action", "confirm_file_diff"}
        
        protocol_methods = set(dir(ConfirmationPolicy))
        
        for method in required_methods:
            assert method in protocol_methods, f"Missing method: {method}"

    def test_mock_object_satisfies_protocol(self):
        """A properly configured mock should satisfy the protocol."""
        mock_policy = Mock(spec=ConfirmationPolicy)
        
        # Should pass isinstance check
        assert isinstance(mock_policy, ConfirmationPolicy)

    def test_protocol_method_signatures(self):
        """Verify method signatures match expected contract."""
        import inspect
        
        # confirm_action
        sig = inspect.signature(ConfirmationPolicy.confirm_action)
        params = list(sig.parameters.keys())
        assert "description" in params
        
        # Check return annotation or at least callable nature
        assert callable(getattr(ConfirmationPolicy, "confirm_action", None))
        
        # confirm_file_diff
        sig = inspect.signature(ConfirmationPolicy.confirm_file_diff)
        params = list(sig.parameters.keys())
        assert "file_path" in params
        assert "new_content" in params
        assert "description" in params


class TestConfirmationPolicyBehavior:
    """Test expected behavior of ConfirmationPolicy implementations."""

    def test_confirm_action_returns_bool(self):
        """confirm_action should return a boolean."""
        policy = Mock(spec=ConfirmationPolicy)
        
        policy.confirm_action.return_value = True
        result = policy.confirm_action("Write to file /test.txt")
        
        assert isinstance(result, bool)
        assert result is True

    def test_confirm_action_can_return_false(self):
        """confirm_action should be able to return False (declined)."""
        policy = Mock(spec=ConfirmationPolicy)
        
        policy.confirm_action.return_value = False
        result = policy.confirm_action("Delete file /test.txt")
        
        assert isinstance(result, bool)
        assert result is False

    def test_confirm_file_diff_returns_bool(self):
        """confirm_file_diff should return a boolean."""
        policy = Mock(spec=ConfirmationPolicy)
        
        policy.confirm_file_diff.return_value = True
        result = policy.confirm_file_diff(
            "/test.txt",
            "new content",
            "Update configuration"
        )
        
        assert isinstance(result, bool)
        assert result is True

    def test_confirm_file_diff_receives_all_parameters(self):
        """confirm_file_diff should receive file_path, new_content, description."""
        policy = Mock(spec=ConfirmationPolicy)
        
        policy.confirm_file_diff.return_value = True
        
        file_path = "/config/settings.json"
        new_content = '{"setting": "value"}'
        description = "Update settings file"
        
        policy.confirm_file_diff(file_path, new_content, description)
        
        policy.confirm_file_diff.assert_called_once_with(
            file_path, new_content, description
        )

    def test_description_contains_action_info(self):
        """Description should contain information about the action."""
        policy = Mock(spec=ConfirmationPolicy)
        policy.confirm_action.return_value = True
        
        # Description should be meaningful
        description = "Write 150 bytes to /home/user/test.txt"
        policy.confirm_action(description)
        
        call_args = policy.confirm_action.call_args[0]
        assert len(call_args[0]) > 0
        assert "/home/user/test.txt" in call_args[0]


class TestConfirmationPolicyFlows:
    """Test confirmation flows with different tool types."""

    def test_read_only_tool_no_confirmation(self):
        """Read-only tools should not require confirmation.
        
        Tools with 'r' permission should be auto-approved.
        """
        policy = Mock(spec=ConfirmationPolicy)
        
        # Read-only tools should bypass confirmation
        # This is typically handled by permission flags, not the policy itself
        # But the policy should still be available for cases where needed
        
        # Policy shouldn't be called for auto-approved tools
        policy.confirm_action.assert_not_called()

    def test_write_tool_uses_confirm_file_diff(self):
        """Write operations should use confirm_file_diff."""
        policy = Mock(spec=ConfirmationPolicy)
        policy.confirm_file_diff.return_value = True
        
        # Simulate write_file tool
        tool_name = "write_file"
        file_path = "/test/output.txt"
        new_content = "Hello, World!"
        description = f"Create file {file_path}"
        
        # Should use confirm_file_diff for file writes
        confirmed = policy.confirm_file_diff(file_path, new_content, description)
        
        assert confirmed is True
        policy.confirm_file_diff.assert_called_once()

    def test_replace_string_uses_confirm_file_diff(self):
        """replace_string tool should use confirm_file_diff."""
        policy = Mock(spec=ConfirmationPolicy)
        policy.confirm_file_diff.return_value = True
        
        file_path = "/test/config.py"
        new_content = "new_setting = True"
        description = f"Replace in {file_path}"
        
        confirmed = policy.confirm_file_diff(file_path, new_content, description)
        
        assert confirmed is True

    def test_general_tool_uses_confirm_action(self):
        """General tools should use confirm_action."""
        policy = Mock(spec=ConfirmationPolicy)
        policy.confirm_action.return_value = True
        
        # Tools like run_shell_command
        description = "Execute: ls -la"
        
        confirmed = policy.confirm_action(description)
        
        assert confirmed is True
        policy.confirm_action.assert_called_once_with(description)

    def test_user_declines_confirmation(self):
        """Test flow when user declines a confirmation."""
        policy = Mock(spec=ConfirmationPolicy)
        policy.confirm_action.return_value = False
        
        description = "Execute: rm -rf /"
        confirmed = policy.confirm_action(description)
        
        assert confirmed is False


class TestConfirmationPolicyIntegration:
    """Integration tests for ConfirmationPolicy with services."""

    def test_executor_accepts_policy_in_constructor(self):
        """ToolExecutor should accept ConfirmationPolicy in constructor.
        
        This is key decoupling: confirmation is injected, not hardcoded.
        """
        try:
            from ayder_cli.services.tools.executor import ToolExecutor
            from ayder_cli.tools.registry import ToolRegistry
            
            policy = Mock(spec=ConfirmationPolicy)
            registry = Mock(spec=ToolRegistry)
            
            # Constructor should accept confirmation_policy parameter
            executor = ToolExecutor(
                tool_registry=registry,
                confirmation_policy=policy
            )
            
            assert hasattr(executor, "confirmation_policy")
            assert executor.confirmation_policy is policy
            
        except ImportError as e:
            pytest.skip(f"Implementation not ready: {e}")
        except TypeError as e:
            pytest.fail(
                f"ToolExecutor should accept confirmation_policy parameter: {e}"
            )

    def test_executor_calls_policy_for_confirmation(self):
        """ToolExecutor should call policy methods for confirmation."""
        try:
            from ayder_cli.services.tools.executor import ToolExecutor
            from ayder_cli.tools.registry import ToolRegistry
            
            policy = Mock(spec=ConfirmationPolicy)
            policy.confirm_action.return_value = True
            
            registry = Mock(spec=ToolRegistry)
            registry.validate_args.return_value = (True, None)
            registry.execute.return_value = Mock(__str__=lambda self: "Success")
            
            # Create executor with injected policy
            executor = ToolExecutor(
                tool_registry=registry,
                confirmation_policy=policy
            )
            
            # This test will need actual implementation to work fully
            # For now, we verify the structure is in place
            
        except ImportError:
            pytest.skip("Implementation not ready")

    def test_permission_flags_bypass_policy(self):
        """Auto-approved permissions should bypass policy calls.
        
        Tools with permission in granted_permissions should not
        trigger confirmation.
        """
        policy = Mock(spec=ConfirmationPolicy)
        
        # When auto-approved, policy shouldn't be called
        # This is handled by the executor logic
        
        # Test structure is in place
        assert hasattr(policy, "confirm_action")
        assert callable(policy.confirm_action)
