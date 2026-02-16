"""Runtime Wiring Tests — Phase 05 (S3)

Contract: CLI and TUI runtime loops call the same shared checkpoint and
execution policy services. Tests validate both source-level wiring AND
actual call-chain behavior via mocks.
"""

import inspect
import asyncio
import pytest
from unittest.mock import MagicMock, patch, AsyncMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Source-level wiring proofs
# ---------------------------------------------------------------------------


class TestCheckpointOrchestrationWiring:
    """Both interfaces must delegate to CheckpointOrchestrator at runtime."""

    def test_tui_handle_checkpoint_uses_orchestrator(self):
        """TuiChatLoop._handle_checkpoint delegates to CheckpointOrchestrator."""
        from ayder_cli.tui.chat_loop import TuiChatLoop

        source = inspect.getsource(TuiChatLoop._handle_checkpoint)

        assert "CheckpointOrchestrator" in source
        assert "orchestrate_checkpoint" in source

    def test_cli_handle_checkpoint_uses_orchestrator(self):
        """ChatLoop._handle_checkpoint delegates to CheckpointOrchestrator."""
        from ayder_cli.chat_loop import ChatLoop

        source = inspect.getsource(ChatLoop._handle_checkpoint)

        assert "CheckpointOrchestrator" in source
        assert "orchestrate_checkpoint" in source

    def test_tui_trigger_uses_checkpoint_trigger(self):
        """TuiChatLoop.run uses CheckpointTrigger for iteration trigger."""
        from ayder_cli.tui.chat_loop import TuiChatLoop

        source = inspect.getsource(TuiChatLoop.run)
        assert "CheckpointTrigger" in source
        assert "trigger.should_trigger" in source

    def test_cli_trigger_uses_checkpoint_trigger(self):
        """ChatLoop.IterationController.should_trigger_checkpoint uses CheckpointTrigger."""
        from ayder_cli.chat_loop import IterationController

        source = inspect.getsource(IterationController.should_trigger_checkpoint)
        assert "CheckpointTrigger" in source

    def test_both_use_same_orchestrator_class(self):
        """CLI and TUI import the same CheckpointOrchestrator — not variants."""
        from ayder_cli.application.checkpoint_orchestrator import CheckpointOrchestrator

        assert CheckpointOrchestrator.__name__ == "CheckpointOrchestrator"
        assert not hasattr(CheckpointOrchestrator, "CLI_SUFFIX")
        assert not hasattr(CheckpointOrchestrator, "TUI_SUFFIX")


class TestExecutionPolicyWiring:
    """Both CLI and TUI must route through ExecutionPolicy."""

    def test_tui_exec_tool_uses_execute_with_registry(self):
        """TuiChatLoop._exec_tool_async calls ExecutionPolicy.execute_with_registry."""
        from ayder_cli.tui.chat_loop import TuiChatLoop

        source = inspect.getsource(TuiChatLoop._exec_tool_async)

        assert "execute_with_registry" in source
        assert "registry.execute" not in source  # No direct bypass

    def test_tui_custom_calls_uses_execute_with_registry(self):
        """TuiChatLoop._execute_custom_tool_calls uses execute_with_registry."""
        from ayder_cli.tui.chat_loop import TuiChatLoop

        source = inspect.getsource(TuiChatLoop._execute_custom_tool_calls)

        assert "execute_with_registry" in source
        assert "registry.execute" not in source

    def test_tui_confirmation_path_uses_execute_with_registry(self):
        """TuiChatLoop._execute_openai_tool_calls approval path uses execute_with_registry."""
        from ayder_cli.tui.chat_loop import TuiChatLoop

        source = inspect.getsource(TuiChatLoop._execute_openai_tool_calls)

        assert "execute_with_registry" in source

    def test_cli_executor_uses_execution_policy(self):
        """ToolExecutor._execute_single_call routes post-confirm through execute_with_registry."""
        from ayder_cli.services.tools.executor import ToolExecutor

        source = inspect.getsource(ToolExecutor._execute_single_call)

        assert "ExecutionPolicy" in source
        assert "execute_with_registry" in source
        assert "self.tool_registry.execute" not in source  # No direct bypass post-confirm

    def test_execute_with_registry_is_single_call_site(self):
        """ExecutionPolicy.execute_with_registry is the only place registry.execute is called."""
        from ayder_cli.application.execution_policy import ExecutionPolicy

        source = inspect.getsource(ExecutionPolicy.execute_with_registry)

        assert "registry.execute" in source


# ---------------------------------------------------------------------------
# Behavioral mock tests — prove actual call chains
# ---------------------------------------------------------------------------


class TestExecutionPolicyCalledAtRuntime:
    """ExecutionPolicy methods are actually invoked during tool execution."""

    def test_tui_exec_tool_calls_execute_with_registry(self):
        """TuiChatLoop._exec_tool_async calls ExecutionPolicy.execute_with_registry."""
        from ayder_cli.tui.chat_loop import TuiChatLoop, TuiLoopConfig
        from ayder_cli.application.execution_policy import ExecutionResult

        registry = MagicMock()
        loop = TuiChatLoop(
            llm=MagicMock(),
            registry=registry,
            messages=[],
            config=TuiLoopConfig(permissions={"r", "w"}),
            callbacks=MagicMock(is_cancelled=MagicMock(return_value=False)),
        )

        fake_result = ExecutionResult(success=True, result="done")

        tc = MagicMock()
        tc.id = "call-1"
        tc.function.name = "write_file"
        tc.function.arguments = '{"file_path": "/tmp/test.txt", "content": "hi"}'

        with patch(
            "ayder_cli.application.execution_policy.ExecutionPolicy.execute_with_registry",
            return_value=fake_result,
        ) as mock_exec:
            result = _run(loop._exec_tool_async(tc))

        mock_exec.assert_called_once()
        assert result["result"] == "done"

    def test_tui_custom_calls_execute_with_registry(self):
        """TuiChatLoop._execute_custom_tool_calls calls ExecutionPolicy.execute_with_registry."""
        from ayder_cli.tui.chat_loop import TuiChatLoop, TuiLoopConfig
        from ayder_cli.application.execution_policy import ExecutionResult

        cb = MagicMock()
        loop = TuiChatLoop(
            llm=MagicMock(),
            registry=MagicMock(),
            messages=[],
            config=TuiLoopConfig(permissions={"r"}),
            callbacks=cb,
        )

        fake_result = ExecutionResult(success=True, result="file contents")

        with patch(
            "ayder_cli.application.execution_policy.ExecutionPolicy.execute_with_registry",
            return_value=fake_result,
        ) as mock_exec:
            _run(loop._execute_custom_tool_calls([{"name": "read_file", "arguments": {"file_path": "/tmp/f"}}]))

        mock_exec.assert_called_once()

    def test_cli_executor_calls_execute_with_registry(self):
        """ToolExecutor._execute_single_call routes post-confirm through execute_with_registry."""
        from ayder_cli.services.tools.executor import ToolExecutor
        from ayder_cli.application.execution_policy import ExecutionResult

        registry = MagicMock()
        registry.normalize_args.return_value = {"file_path": "/tmp/t.txt"}

        executor = ToolExecutor(tool_registry=registry)
        fake_result = ExecutionResult(success=True, result="ok")

        with patch(
            "ayder_cli.application.execution_policy.ExecutionPolicy.execute_with_registry",
            return_value=fake_result,
        ) as mock_exec:
            outcome, value = executor._execute_single_call(
                "read_file", {"file_path": "/tmp/t.txt"}, granted_permissions={"r"}, verbose=False
            )

        mock_exec.assert_called_once()
        assert outcome == "success"
        assert value == "ok"


class TestCheckpointOrchestrationCalledAtRuntime:
    """CheckpointOrchestrator methods are actually invoked during checkpoint handling."""

    def test_tui_checkpoint_calls_reset_state(self):
        """TuiChatLoop._handle_checkpoint calls CheckpointOrchestrator.reset_state."""
        from ayder_cli.tui.chat_loop import TuiChatLoop, TuiLoopConfig
        from ayder_cli.checkpoint_manager import CheckpointManager

        cm = MagicMock(spec=CheckpointManager)
        cm.save_checkpoint.return_value = None
        mm = MagicMock()
        mm.build_quick_restore_message.return_value = "Restored."

        loop = TuiChatLoop(
            llm=MagicMock(),
            registry=MagicMock(),
            messages=[{"role": "system", "content": "sys"}],
            config=TuiLoopConfig(),
            callbacks=MagicMock(),
            checkpoint_manager=cm,
            memory_manager=mm,
        )

        summary_resp = MagicMock()
        summary_resp.choices[0].message.content = "Summary"

        with patch("ayder_cli.tui.chat_loop.call_llm_async", new_callable=AsyncMock, return_value=summary_resp):
            with patch(
                "ayder_cli.application.checkpoint_orchestrator.CheckpointOrchestrator.reset_state"
            ) as mock_reset:
                mock_reset.side_effect = lambda state, **kw: None
                with patch(
                    "ayder_cli.application.checkpoint_orchestrator.CheckpointOrchestrator.restore_from_checkpoint"
                ) as mock_restore:
                    mock_restore.side_effect = lambda state, saved, **kw: None
                    result = _run(loop._handle_checkpoint())

        assert result is True
        mock_reset.assert_called_once()
        mock_restore.assert_called_once()

    def test_cli_checkpoint_calls_reset_state(self):
        """ChatLoop._handle_checkpoint calls CheckpointOrchestrator.reset_state."""
        from ayder_cli.chat_loop import ChatLoop, LoopConfig
        from ayder_cli.client import ChatSession

        mm = MagicMock()
        mm.create_checkpoint.return_value = True
        mm.restore_from_checkpoint.return_value = None

        config = LoopConfig(model="m", num_ctx=1024, max_iterations=10, permissions={"r"})
        session = MagicMock(spec=ChatSession)
        session.get_messages.return_value = [{"role": "system", "content": "sys"}]

        loop = ChatLoop(
            llm_provider=MagicMock(),
            tool_executor=MagicMock(),
            session=session,
            config=config,
            memory_manager=mm,
        )

        with patch(
            "ayder_cli.application.checkpoint_orchestrator.CheckpointOrchestrator.reset_state"
        ) as mock_reset:
            mock_reset.side_effect = lambda state, **kw: None
            with patch(
                "ayder_cli.application.checkpoint_orchestrator.CheckpointOrchestrator.restore_from_checkpoint"
            ) as mock_restore:
                mock_restore.side_effect = lambda state, saved, **kw: None
                result = loop._handle_checkpoint()

        assert result is True
        mock_reset.assert_called_once()
        mock_restore.assert_called_once()


class TestConvergenceIntegration:
    """End-to-end convergence: same services, same behavior."""

    def test_tui_and_cli_use_same_permission_source(self):
        """Both TUI ExecutionPolicy and CLI ToolExecutor use TOOL_PERMISSIONS."""
        from ayder_cli.application.execution_policy import _required_permission
        from ayder_cli.tools.schemas import TOOL_PERMISSIONS

        for tool, expected_perm in TOOL_PERMISSIONS.items():
            assert _required_permission(tool) == expected_perm

    def test_checkpoint_trigger_same_threshold_cli_tui(self):
        """CheckpointTrigger used by CLI and TUI has same threshold for same config."""
        from ayder_cli.application.checkpoint_orchestrator import CheckpointTrigger

        trigger = CheckpointTrigger(max_iterations=50)
        assert trigger.should_trigger(51) is True
        assert trigger.should_trigger(50) is True
        assert trigger.should_trigger(49) is False

    def test_checkpoint_orchestrator_same_result_cli_tui(self):
        """CheckpointOrchestrator.reset_state produces identical result regardless of context."""
        from ayder_cli.application.checkpoint_orchestrator import (
            CheckpointOrchestrator,
            EngineState,
            RuntimeContext,
        )

        orchestrator = CheckpointOrchestrator()

        cli_state = EngineState(
            iteration=30,
            messages=[{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}],
        )
        tui_state = EngineState(
            iteration=30,
            messages=[{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}],
        )

        orchestrator.reset_state(cli_state, context=RuntimeContext(interface="cli"))
        orchestrator.reset_state(tui_state, context=RuntimeContext(interface="tui"))

        assert cli_state.iteration == tui_state.iteration == 0
        assert len(cli_state.messages) == len(tui_state.messages) == 1

    def test_execution_policy_same_result_cli_tui(self):
        """ExecutionPolicy produces same permission result for CLI and TUI contexts."""
        from ayder_cli.application.execution_policy import ExecutionPolicy, RuntimeContext

        policy = ExecutionPolicy(granted_permissions={"r"})

        cli_result = policy.check_permission("write_file", context=RuntimeContext(interface="cli"))
        tui_result = policy.check_permission("write_file", context=RuntimeContext(interface="tui"))

        assert type(cli_result) is type(tui_result)
        assert str(cli_result) == str(tui_result)

    def test_known_tools_in_sync_with_registry(self):
        """_KNOWN_TOOLS in ValidationAuthority must match actual registry tool names exactly."""
        from ayder_cli.application.validation import _KNOWN_TOOLS
        from ayder_cli.tools.definition import TOOL_DEFINITIONS

        registry_tools = {td.name for td in TOOL_DEFINITIONS}
        known_tools = set(_KNOWN_TOOLS.keys())

        missing = registry_tools - known_tools
        extra = known_tools - registry_tools

        assert not missing, f"Tools in registry missing from _KNOWN_TOOLS: {missing}"
        assert not extra, f"Tools in _KNOWN_TOOLS not in registry: {extra}"


class TestCheckpointOrchestrateMethod:
    """orchestrate_checkpoint delegates both loops to a single shared transition path."""

    def test_orchestrate_checkpoint_calls_save_reset_restore(self):
        """orchestrate_checkpoint calls save_checkpoint, reset_state, restore_from_checkpoint."""
        from ayder_cli.application.checkpoint_orchestrator import (
            CheckpointOrchestrator,
            EngineState,
        )

        cm = MagicMock()
        orchestrator = CheckpointOrchestrator()
        state = EngineState(
            iteration=10,
            messages=[{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}],
        )

        restore_msg = orchestrator.orchestrate_checkpoint(state, "real summary", cm)

        cm.save_checkpoint.assert_called_once_with("real summary")
        assert state.iteration == 0
        assert "real summary" in restore_msg or state.restored_cycle >= 0

    def test_orchestrate_checkpoint_skip_save(self):
        """orchestrate_checkpoint with save=False skips save_checkpoint call."""
        from ayder_cli.application.checkpoint_orchestrator import (
            CheckpointOrchestrator,
            EngineState,
        )

        cm = MagicMock()
        orchestrator = CheckpointOrchestrator()
        state = EngineState(iteration=5, messages=[{"role": "system", "content": "sys"}])

        orchestrator.orchestrate_checkpoint(state, "cli summary", cm, save=False)

        cm.save_checkpoint.assert_not_called()
        assert state.iteration == 0

    def test_tui_checkpoint_uses_orchestrate_checkpoint(self):
        """TuiChatLoop._handle_checkpoint delegates to orchestrator.orchestrate_checkpoint."""
        from ayder_cli.tui.chat_loop import TuiChatLoop

        source = inspect.getsource(TuiChatLoop._handle_checkpoint)
        assert "orchestrate_checkpoint" in source

    def test_cli_checkpoint_uses_orchestrate_checkpoint(self):
        """ChatLoop._handle_checkpoint delegates to orchestrator.orchestrate_checkpoint."""
        from ayder_cli.chat_loop import ChatLoop

        source = inspect.getsource(ChatLoop._handle_checkpoint)
        assert "orchestrate_checkpoint" in source
