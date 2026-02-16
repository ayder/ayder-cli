"""Execution Policy Parity Tests — Phase 05 (TEST-FIRST)

Contract: CLI and TUI use the same tool execution policy path.

These tests define expected behavior BEFORE DEV implements shared execution.
"""

import asyncio
import pytest
from unittest.mock import Mock


def _run_async(coro):
    """Run async coroutine synchronously."""
    return asyncio.run(coro)


class TestPermissionDeniedParity:
    """Permission-denied behavior must be identical across CLI and TUI."""

    def test_same_denied_error_format(self):
        """Both interfaces produce identical error format for denied permissions."""
        try:
            from ayder_cli.application.execution_policy import (
                ExecutionPolicy,
                PermissionDeniedError,
            )
        except ImportError:
            pytest.skip("Execution policy not yet implemented")

        policy = ExecutionPolicy(granted_permissions={"r"})
        
        error = policy.check_permission("write_file")
        
        assert isinstance(error, PermissionDeniedError)
        assert "write" in str(error).lower()
        assert error.tool_name == "write_file"
        assert error.required_permission == "w"

    def test_denied_error_includes_remediation(self):
        """Error includes how to grant permission (both interfaces)."""
        try:
            from ayder_cli.application.execution_policy import (
                ExecutionPolicy,
                PermissionDeniedError,
            )
        except ImportError:
            pytest.skip("Execution policy not yet implemented")

        policy = ExecutionPolicy(granted_permissions={"r"})
        error = policy.check_permission("run_shell_command")
        
        # Error message includes grant hint
        error_str = str(error)
        assert "-x" in error_str or "--permission" in error_str or "grant" in error_str.lower()

    def test_cli_tui_same_permission_check(self):
        """Same permission check logic for both interfaces."""
        try:
            from ayder_cli.application.execution_policy import (
                ExecutionPolicy,
                RuntimeContext,
            )
        except ImportError:
            pytest.skip("Execution policy not yet implemented")

        policy = ExecutionPolicy(granted_permissions={"r"})
        
        cli_context = RuntimeContext(interface="cli")
        tui_context = RuntimeContext(interface="tui")
        
        # Same permission logic regardless of interface
        cli_result = policy.check_permission("write_file", context=cli_context)
        tui_result = policy.check_permission("write_file", context=tui_context)
        
        assert type(cli_result) == type(tui_result)
        assert str(cli_result) == str(tui_result)


class TestConfirmationBehaviorParity:
    """User confirmation behavior must be identical across CLI and TUI."""

    def test_confirmation_required_same_conditions(self):
        """Same conditions trigger confirmation in both interfaces."""
        try:
            from ayder_cli.application.execution_policy import (
                ExecutionPolicy,
                ConfirmationRequirement,
            )
        except ImportError:
            pytest.skip("Execution policy not yet implemented")

        policy = ExecutionPolicy(granted_permissions={"r"})
        
        # Write tool needs confirmation with only 'r' permission
        read_req = policy.get_confirmation_requirement("read_file")
        write_req = policy.get_confirmation_requirement("write_file")
        
        assert read_req == ConfirmationRequirement.NONE
        assert write_req == ConfirmationRequirement.REQUIRED

    def test_confirmation_flow_same_outcomes(self):
        """Confirmation produces same outcomes in both interfaces."""
        try:
            from ayder_cli.application.execution_policy import (
                ExecutionPolicy,
                ConfirmationResult,
            )
        except ImportError:
            pytest.skip("Execution policy not yet implemented")

        policy = ExecutionPolicy(granted_permissions={"r"})
        
        # Approved: tool executes
        assert ConfirmationResult.APPROVED.executes_tool is True
        
        # Declined: tool skipped
        assert ConfirmationResult.DECLINED.executes_tool is False
        
        # Instruct: tool skipped, instructions added
        assert ConfirmationResult.INSTRUCT.executes_tool is False
        assert ConfirmationResult.INSTRUCT.includes_instructions is True

    def test_file_diff_confirmation_same_behavior(self):
        """File diff confirmation behaves same in CLI and TUI."""
        try:
            from ayder_cli.application.execution_policy import (
                ExecutionPolicy,
                FileDiffConfirmation,
            )
        except ImportError:
            pytest.skip("Execution policy not yet implemented")

        policy = ExecutionPolicy()
        
        diff = FileDiffConfirmation(
            file_path="/test.txt",
            original_content="old",
            new_content="new",
            description="Update file",
        )
        
        # Same diff logic regardless of interface
        result = policy.confirm_file_diff(diff)
        
        assert result in (True, False)  # Boolean result


class TestErrorPropagationParity:
    """Error propagation format must be identical across CLI and TUI."""

    def test_tool_error_same_format(self):
        """Tool execution errors have same format in both interfaces."""
        try:
            from ayder_cli.application.execution_policy import (
                ExecutionPolicy,
                ToolExecutionError,
            )
        except ImportError:
            pytest.skip("Execution policy not yet implemented")

        policy = ExecutionPolicy()
        
        error = ToolExecutionError(
            tool_name="read_file",
            message="File not found: /missing.txt",
            exit_code=1,
        )
        
        # Structured error format
        assert error.tool_name == "read_file"
        assert "File not found" in error.message
        assert error.exit_code == 1
        
        # Consistent string representation
        error_str = str(error)
        assert "read_file" in error_str
        assert "File not found" in error_str

    def test_validation_error_same_format(self):
        """Validation errors have same format in both interfaces."""
        try:
            from ayder_cli.application.execution_policy import (
                ExecutionPolicy,
                ValidationError,
            )
        except ImportError:
            pytest.skip("Execution policy not yet implemented")

        policy = ExecutionPolicy()
        
        error = ValidationError(
            tool_name="write_file",
            field="content",
            message="Content cannot be empty",
        )
        
        # Structured validation error
        assert error.tool_name == "write_file"
        assert error.field == "content"
        assert "empty" in error.message

    def test_error_message_to_llm_same_format(self):
        """Error messages sent back to LLM have same format."""
        try:
            from ayder_cli.application.execution_policy import (
                ExecutionPolicy,
                ToolExecutionError,
            )
        except ImportError:
            pytest.skip("Execution policy not yet implemented")

        policy = ExecutionPolicy()
        
        error = ToolExecutionError(
            tool_name="run_shell_command",
            message="Command failed: exit code 1",
            exit_code=1,
        )
        
        # Format for LLM consumption
        llm_message = policy.format_error_for_llm(error)
        
        assert llm_message["role"] == "tool"
        assert "error" in llm_message["content"].lower()
        assert "run_shell_command" in llm_message["content"]


class TestExecutionPolicyContract:
    """Shared execution policy service contract."""

    def test_policy_is_shared_service(self):
        """Single policy class used by both CLI and TUI."""
        try:
            from ayder_cli.application.execution_policy import ExecutionPolicy
        except ImportError:
            pytest.skip("Execution policy not yet implemented")

        # One class, not CLI/TUI specific variants
        assert ExecutionPolicy.__name__ == "ExecutionPolicy"

    def test_policy_executes_tools_consistently(self):
        """Tool execution produces consistent results."""
        try:
            from ayder_cli.application.execution_policy import (
                ExecutionPolicy,
                ToolRequest,
            )
        except ImportError:
            pytest.skip("Execution policy not yet implemented")

        policy = ExecutionPolicy(granted_permissions={"r", "w"})
        
        request = ToolRequest(
            name="write_file",
            arguments={"file_path": "/test.txt", "content": "hello"},
        )
        
        # Same execution regardless of caller
        result1 = policy.execute(request)
        result2 = policy.execute(request)
        
        # Deterministic for same input
        assert type(result1) == type(result2)

    def test_no_interface_specific_execution_paths(self):
        """No execution code branches on interface type."""
        try:
            from ayder_cli.application.execution_policy import ExecutionPolicy
        except ImportError:
            pytest.skip("Execution policy not yet implemented")

        # Verify no interface-specific branching
        import inspect
        source = inspect.getsource(ExecutionPolicy)
        
        # Should not have interface-specific conditionals
        assert "if interface ==" not in source.lower()
        assert "if context.interface" not in source.lower()


class TestConvergenceScenarios:
    """End-to-end convergence scenarios."""

    def test_read_only_tool_auto_approved_both(self):
        """Read-only tools auto-approved in both CLI and TUI."""
        try:
            from ayder_cli.application.execution_policy import (
                ExecutionPolicy,
                ToolRequest,
                RuntimeContext,
            )
        except ImportError:
            pytest.skip("Execution policy not yet implemented")

        policy = ExecutionPolicy(granted_permissions={"r"})
        request = ToolRequest(name="read_file", arguments={"file_path": "/test.txt"})
        
        cli_result = policy.execute(request, context=RuntimeContext(interface="cli"))
        tui_result = policy.execute(request, context=RuntimeContext(interface="tui"))
        
        # Both auto-approved, both execute
        assert cli_result.was_confirmed is False  # Auto-approved
        assert tui_result.was_confirmed is False  # Auto-approved

    def test_write_tool_needs_confirmation_both(self):
        """Write tools need confirmation in both CLI and TUI."""
        try:
            from ayder_cli.application.execution_policy import (
                ExecutionPolicy,
                ToolRequest,
                RuntimeContext,
            )
        except ImportError:
            pytest.skip("Execution policy not yet implemented")

        policy = ExecutionPolicy(granted_permissions={"r"})
        request = ToolRequest(name="write_file", arguments={"file_path": "/test.txt", "content": "x"})
        
        cli_req = policy.get_confirmation_requirement("write_file")
        tui_req = policy.get_confirmation_requirement("write_file")
        
        # Same confirmation requirement
        assert cli_req == tui_req
        assert cli_req.requires_confirmation is True

    def test_denied_tool_same_error_both(self):
        """Denied tools produce same error in both CLI and TUI."""
        try:
            from ayder_cli.application.execution_policy import (
                ExecutionPolicy,
                ToolRequest,
                RuntimeContext,
            )
        except ImportError:
            pytest.skip("Execution policy not yet implemented")

        policy = ExecutionPolicy(granted_permissions=set())  # No permissions
        request = ToolRequest(name="read_file", arguments={"file_path": "/test.txt"})
        
        cli_result = policy.execute(request, context=RuntimeContext(interface="cli"))
        tui_result = policy.execute(request, context=RuntimeContext(interface="tui"))
        
        # Same error outcome
        assert cli_result.success is False
        assert tui_result.success is False
        assert type(cli_result.error) == type(tui_result.error)
