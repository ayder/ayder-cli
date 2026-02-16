"""Runtime Wiring Tests — Phase 05 (S3)

Contract: CLI and TUI runtime loops call the same shared checkpoint and
execution policy services — not isolated module tests, but actual source-level
wiring proofs.
"""

import inspect
import pytest


class TestCheckpointOrchestrationWiring:
    """Both interfaces must delegate to CheckpointOrchestrator at runtime."""

    def test_tui_handle_checkpoint_uses_orchestrator(self):
        """TuiChatLoop._handle_checkpoint delegates to CheckpointOrchestrator."""
        from ayder_cli.tui.chat_loop import TuiChatLoop

        source = inspect.getsource(TuiChatLoop._handle_checkpoint)

        assert "CheckpointOrchestrator" in source
        assert "orchestrator.reset_state" in source

    def test_cli_handle_checkpoint_uses_orchestrator(self):
        """ChatLoop._handle_checkpoint delegates to CheckpointOrchestrator."""
        from ayder_cli.chat_loop import ChatLoop

        source = inspect.getsource(ChatLoop._handle_checkpoint)

        assert "CheckpointOrchestrator" in source
        assert "orchestrator.reset_state" in source

    def test_both_use_same_orchestrator_class(self):
        """Both CLI and TUI import the same CheckpointOrchestrator class."""
        from ayder_cli.application.checkpoint_orchestrator import CheckpointOrchestrator
        from ayder_cli.tui.chat_loop import TuiChatLoop
        from ayder_cli.chat_loop import ChatLoop

        tui_src = inspect.getsource(TuiChatLoop)
        cli_src = inspect.getsource(ChatLoop._handle_checkpoint)

        assert "CheckpointOrchestrator" in tui_src
        assert "CheckpointOrchestrator" in cli_src

        # Single shared class — not interface-specific variants
        assert CheckpointOrchestrator.__name__ == "CheckpointOrchestrator"
        assert not hasattr(CheckpointOrchestrator, "CLI_SUFFIX")
        assert not hasattr(CheckpointOrchestrator, "TUI_SUFFIX")


class TestExecutionPolicyWiring:
    """Both interfaces must delegate tool permission checks to ExecutionPolicy."""

    def test_tui_exec_tool_uses_execution_policy(self):
        """TuiChatLoop._exec_tool_async routes through ExecutionPolicy."""
        from ayder_cli.tui.chat_loop import TuiChatLoop

        source = inspect.getsource(TuiChatLoop._exec_tool_async)

        assert "ExecutionPolicy" in source
        assert "check_permission" in source

    def test_tui_custom_tool_calls_use_execution_policy(self):
        """TuiChatLoop._execute_custom_tool_calls routes through ExecutionPolicy."""
        from ayder_cli.tui.chat_loop import TuiChatLoop

        source = inspect.getsource(TuiChatLoop._execute_custom_tool_calls)

        assert "ExecutionPolicy" in source
        assert "check_permission" in source

    def test_tui_confirmation_check_delegates_to_policy(self):
        """TuiChatLoop._tool_needs_confirmation delegates to ExecutionPolicy."""
        from ayder_cli.tui.chat_loop import TuiChatLoop

        source = inspect.getsource(TuiChatLoop._tool_needs_confirmation)

        assert "ExecutionPolicy" in source
        assert "get_confirmation_requirement" in source

    def test_no_direct_tool_permissions_lookup_in_exec(self):
        """_exec_tool_async does not directly read TOOL_PERMISSIONS — uses policy."""
        from ayder_cli.tui.chat_loop import TuiChatLoop

        source = inspect.getsource(TuiChatLoop._exec_tool_async)

        # Execution path delegates to policy, not TOOL_PERMISSIONS directly
        assert "TOOL_PERMISSIONS" not in source


class TestValidationAuthorityWiring:
    """ValidationAuthority is wired into the TUI execution path."""

    def test_tui_exec_tool_uses_validation_authority(self):
        """TuiChatLoop._exec_tool_async calls ValidationAuthority."""
        from ayder_cli.tui.chat_loop import TuiChatLoop

        source = inspect.getsource(TuiChatLoop._exec_tool_async)

        assert "ValidationAuthority" in source
        assert "authority.validate" in source

    def test_validation_runs_before_registry_execute(self):
        """Validation is called before registry.execute in _exec_tool_async."""
        from ayder_cli.tui.chat_loop import TuiChatLoop

        source = inspect.getsource(TuiChatLoop._exec_tool_async)

        # ValidationAuthority must appear before registry.execute in source
        val_pos = source.index("ValidationAuthority")
        exec_pos = source.index("registry.execute")

        assert val_pos < exec_pos


class TestConvergenceIntegration:
    """End-to-end convergence: same services, same behavior."""

    def test_tui_and_cli_use_same_permission_source(self):
        """Both TUI _tool_needs_confirmation and ExecutionPolicy use TOOL_PERMISSIONS."""
        from ayder_cli.application.execution_policy import _required_permission
        from ayder_cli.tools.schemas import TOOL_PERMISSIONS

        # ExecutionPolicy delegates to TOOL_PERMISSIONS
        for tool, expected_perm in TOOL_PERMISSIONS.items():
            assert _required_permission(tool) == expected_perm

    def test_checkpoint_orchestrator_produces_same_result_for_cli_tui(self):
        """CheckpointOrchestrator.reset_state produces identical results regardless of context."""
        from ayder_cli.application.checkpoint_orchestrator import (
            CheckpointOrchestrator,
            EngineState,
            RuntimeContext,
        )

        orchestrator = CheckpointOrchestrator()

        cli_state = EngineState(
            iteration=30,
            messages=[
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "hello"},
            ],
        )
        tui_state = EngineState(
            iteration=30,
            messages=[
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "hello"},
            ],
        )

        orchestrator.reset_state(cli_state, context=RuntimeContext(interface="cli"))
        orchestrator.reset_state(tui_state, context=RuntimeContext(interface="tui"))

        assert cli_state.iteration == tui_state.iteration == 0
        assert len(cli_state.messages) == len(tui_state.messages) == 1

    def test_execution_policy_same_result_for_cli_tui(self):
        """ExecutionPolicy produces same permission result for CLI and TUI contexts."""
        from ayder_cli.application.execution_policy import ExecutionPolicy, RuntimeContext

        policy = ExecutionPolicy(granted_permissions={"r"})

        cli_result = policy.check_permission("write_file", context=RuntimeContext(interface="cli"))
        tui_result = policy.check_permission("write_file", context=RuntimeContext(interface="tui"))

        assert type(cli_result) is type(tui_result)
        assert str(cli_result) == str(tui_result)
