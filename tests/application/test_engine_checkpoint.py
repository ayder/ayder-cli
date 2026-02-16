"""Checkpoint and Memory Integration Tests for Shared Async Engine.

Phase 04 - Shared Async Engine must integrate with checkpoint/memory.

Note: Tests use asyncio.run() wrapper instead of pytest.mark.asyncio
to avoid plugin dependency issues.
"""

import asyncio
import pytest
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock


# ---------------------------------------------------------------------------
# Test Fixtures
# ---------------------------------------------------------------------------


def _run_async(coro):
    """Helper to run async coroutine in sync test."""
    return asyncio.run(coro)


@dataclass
class FakeCheckpoint:
    """Fake checkpoint for testing."""
    messages: list
    metadata: dict


# ---------------------------------------------------------------------------
# Checkpoint Integration Tests
# ---------------------------------------------------------------------------


class TestCheckpointIntegration:
    """Contract: Engine integrates with CheckpointManager."""

    def test_engine_accepts_checkpoint_manager(self):
        """Engine must accept checkpoint_manager parameter."""
        pytest.importorskip("ayder_cli.application.agent_engine",
                           reason="Engine not yet implemented")
        from ayder_cli.application.agent_engine import AgentEngine
        
        import inspect
        sig = inspect.signature(AgentEngine.__init__)
        
        # checkpoint_manager should be optional parameter
        assert "checkpoint_manager" in sig.parameters, \
            "AgentEngine must accept checkpoint_manager parameter"

    def test_checkpoint_triggered_at_max_iterations(self):
        """Engine should trigger checkpoint when max iterations reached."""
        pytest.importorskip("ayder_cli.application.agent_engine",
                           reason="Engine not yet implemented")
        from ayder_cli.application.agent_engine import AgentEngine, EngineConfig
        
        llm = MagicMock()
        registry = MagicMock()
        registry.get_schemas.return_value = []
        registry.execute.return_value = "content"
        
        # Always return tool response to force continued iteration
        call_count = [0]
        
        async def fake_llm(*args, **kwargs):
            call_count[0] += 1
            return MagicMock(
                choices=[MagicMock(message=MagicMock(
                    content="",
                    tool_calls=[MagicMock(
                        id=f"tc{call_count[0]}",
                        type="function",
                        function=MagicMock(name="read_file", arguments='{"file_path":"/test"}')
                    )]
                ))],
                usage=MagicMock(total_tokens=10)
            )
        
        llm.chat = fake_llm
        
        checkpoint_manager = MagicMock()
        checkpoint_manager.has_saved_checkpoint.return_value = False
        checkpoint_manager.save_checkpoint.return_value = FakeCheckpoint(
            messages=[], metadata={}
        )
        
        memory_manager = MagicMock()
        memory_manager.create_checkpoint.return_value = True
        
        callbacks = MagicMock()
        callbacks.is_cancelled.return_value = False
        
        engine = AgentEngine(
            llm_provider=llm,
            tool_registry=registry,
            config=EngineConfig(max_iterations=3, permissions={"r"}),
            callbacks=callbacks,
            checkpoint_manager=checkpoint_manager,
            memory_manager=memory_manager,
        )
        
        async def _test():
            messages = [{"role": "system", "content": "sys"}]
            await engine.run(messages)
        
        _run_async(_test())
        
        # Checkpoint should be created when max iterations approached
        # Either memory_manager or checkpoint_manager should be involved
        assert memory_manager.create_checkpoint.called or checkpoint_manager.save_checkpoint.called, \
            "Checkpoint must be triggered via memory_manager or checkpoint_manager"

    def test_checkpoint_restores_and_continues(self):
        """Engine should restore from checkpoint and continue loop."""
        pytest.importorskip("ayder_cli.application.agent_engine",
                           reason="Engine not yet implemented")
        from ayder_cli.application.agent_engine import AgentEngine, EngineConfig
        
        llm = MagicMock()
        registry = MagicMock()
        callbacks = MagicMock()
        callbacks.is_cancelled.return_value = False
        
        checkpoint_manager = MagicMock()
        checkpoint_manager.has_saved_checkpoint.return_value = True
        
        memory_manager = MagicMock()
        memory_manager.restore_from_checkpoint = MagicMock()
        memory_manager.build_quick_restore_message.return_value = "Restored context"
        
        engine = AgentEngine(
            llm_provider=llm,
            tool_registry=registry,
            config=EngineConfig(max_iterations=5),
            callbacks=callbacks,
            checkpoint_manager=checkpoint_manager,
            memory_manager=memory_manager,
        )
        
        messages = [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}]
        
        # Mock LLM to return text after checkpoint
        llm.chat = AsyncMock(return_value=MagicMock(
            choices=[MagicMock(message=MagicMock(content="Response", tool_calls=None))],
            usage=MagicMock(total_tokens=10)
        ))
        
        async def _test():
            await engine.run(messages)
        
        _run_async(_test())
        
        # Memory restore should be called
        assert memory_manager.restore_from_checkpoint.called, \
            "Memory manager restore_from_checkpoint must be called"


# ---------------------------------------------------------------------------
# Memory Manager Integration Tests
# ---------------------------------------------------------------------------


class TestMemoryManagerIntegration:
    """Contract: Engine integrates with MemoryManager."""

    def test_engine_accepts_memory_manager(self):
        """Engine must accept memory_manager parameter."""
        pytest.importorskip("ayder_cli.application.agent_engine",
                           reason="Engine not yet implemented")
        from ayder_cli.application.agent_engine import AgentEngine
        
        import inspect
        sig = inspect.signature(AgentEngine.__init__)
        
        assert "memory_manager" in sig.parameters, \
            "AgentEngine must accept memory_manager parameter"

    def test_memory_manager_creates_checkpoint(self):
        """Memory manager should create checkpoint when needed."""
        pytest.importorskip("ayder_cli.application.agent_engine",
                           reason="Engine not yet implemented")
        from ayder_cli.application.agent_engine import AgentEngine, EngineConfig
        
        llm = MagicMock()
        registry = MagicMock()
        callbacks = MagicMock()
        callbacks.is_cancelled.return_value = False
        
        memory_manager = MagicMock()
        memory_manager.create_checkpoint.return_value = True
        
        checkpoint_manager = MagicMock()
        checkpoint_manager.has_saved_checkpoint.return_value = False
        
        engine = AgentEngine(
            llm_provider=llm,
            tool_registry=registry,
            config=EngineConfig(max_iterations=2),
            callbacks=callbacks,
            checkpoint_manager=checkpoint_manager,
            memory_manager=memory_manager,
        )
        
        # Mock LLM to iterate multiple times
        call_count = [0]
        
        async def fake_llm(*args, **kwargs):
            call_count[0] += 1
            return MagicMock(
                choices=[MagicMock(message=MagicMock(
                    content="",
                    tool_calls=[MagicMock(
                        id=f"tc{call_count[0]}",
                        type="function",
                        function=MagicMock(name="read_file", arguments='{}')
                    )]
                ))],
                usage=MagicMock(total_tokens=10)
            )
        
        llm.chat = fake_llm
        registry.execute.return_value = "result"
        
        async def _test():
            messages = [{"role": "system", "content": "sys"}]
            await engine.run(messages)
        
        _run_async(_test())
        
        # Memory manager should be involved in checkpoint flow
        assert memory_manager.create_checkpoint.called or checkpoint_manager.save_checkpoint.called, \
            "Checkpoint creation must involve memory_manager or checkpoint_manager"


# ---------------------------------------------------------------------------
# Callbacks Integration Tests
# ---------------------------------------------------------------------------


class TestCallbacksIntegration:
    """Contract: Engine properly invokes callbacks."""

    def test_thinking_callbacks(self):
        """Engine must call thinking_start and thinking_stop."""
        pytest.importorskip("ayder_cli.application.agent_engine",
                           reason="Engine not yet implemented")
        from ayder_cli.application.agent_engine import AgentEngine, EngineConfig
        
        llm = MagicMock()
        llm.chat = AsyncMock(return_value=MagicMock(
            choices=[MagicMock(message=MagicMock(content="Response", tool_calls=None))],
            usage=MagicMock(total_tokens=10)
        ))
        
        callbacks = MagicMock()
        callbacks.is_cancelled.return_value = False
        
        engine = AgentEngine(
            llm_provider=llm,
            tool_registry=MagicMock(),
            config=EngineConfig(),
            callbacks=callbacks,
        )
        
        async def _test():
            await engine.run([{"role": "system", "content": "sys"}])
        
        _run_async(_test())
        
        callbacks.on_thinking_start.assert_called_once()
        callbacks.on_thinking_stop.assert_called_once()

    def test_iteration_callback(self):
        """Engine must call on_iteration_update."""
        pytest.importorskip("ayder_cli.application.agent_engine",
                           reason="Engine not yet implemented")
        from ayder_cli.application.agent_engine import AgentEngine, EngineConfig
        
        llm = MagicMock()
        llm.chat = AsyncMock(return_value=MagicMock(
            choices=[MagicMock(message=MagicMock(content="Response", tool_calls=None))],
            usage=MagicMock(total_tokens=10)
        ))
        
        callbacks = MagicMock()
        callbacks.is_cancelled.return_value = False
        
        engine = AgentEngine(
            llm_provider=llm,
            tool_registry=MagicMock(),
            config=EngineConfig(),
            callbacks=callbacks,
        )
        
        async def _test():
            await engine.run([{"role": "system", "content": "sys"}])
        
        _run_async(_test())
        
        callbacks.on_iteration_update.assert_called()

    def test_token_usage_callback(self):
        """Engine must call on_token_usage with total tokens."""
        pytest.importorskip("ayder_cli.application.agent_engine",
                           reason="Engine not yet implemented")
        from ayder_cli.application.agent_engine import AgentEngine, EngineConfig
        
        llm = MagicMock()
        llm.chat = AsyncMock(return_value=MagicMock(
            choices=[MagicMock(message=MagicMock(content="Response", tool_calls=None))],
            usage=MagicMock(total_tokens=42)
        ))
        
        callbacks = MagicMock()
        callbacks.is_cancelled.return_value = False
        
        engine = AgentEngine(
            llm_provider=llm,
            tool_registry=MagicMock(),
            config=EngineConfig(),
            callbacks=callbacks,
        )
        
        async def _test():
            await engine.run([{"role": "system", "content": "sys"}])
        
        _run_async(_test())
        
        callbacks.on_token_usage.assert_called_with(42)

    def test_confirmation_callback(self):
        """Engine must call request_confirmation for non-approved tools."""
        pytest.importorskip("ayder_cli.application.agent_engine",
                           reason="Engine not yet implemented")
        from ayder_cli.application.agent_engine import AgentEngine, EngineConfig
        
        llm = MagicMock()
        llm.chat = AsyncMock(return_value=MagicMock(
            choices=[MagicMock(message=MagicMock(
                content="",
                tool_calls=[MagicMock(
                    id="tc1",
                    type="function",
                    function=MagicMock(name="write_file", arguments='{"file_path":"/test"}')
                )]
            ))],
            usage=MagicMock(total_tokens=10)
        ))
        
        callbacks = MagicMock()
        callbacks.is_cancelled.return_value = False
        callbacks.request_confirmation = AsyncMock(return_value={"action": "approve"})
        
        registry = MagicMock()
        registry.get_schemas.return_value = []
        registry.execute.return_value = "done"
        
        engine = AgentEngine(
            llm_provider=llm,
            tool_registry=registry,
            config=EngineConfig(permissions={"r"}),  # No 'w' permission
            callbacks=callbacks,
        )
        
        async def _test():
            await engine.run([{"role": "system", "content": "sys"}])
        
        _run_async(_test())
        
        callbacks.request_confirmation.assert_awaited_once()


# ---------------------------------------------------------------------------
# Tool Execution Integration Tests
# ---------------------------------------------------------------------------


class TestToolExecutionIntegration:
    """Contract: Engine properly executes tools through registry."""

    def test_tool_execution_calls_registry(self):
        """Engine must call registry.execute for tool calls."""
        pytest.importorskip("ayder_cli.application.agent_engine",
                           reason="Engine not yet implemented")
        from ayder_cli.application.agent_engine import AgentEngine, EngineConfig
        
        llm = MagicMock()
        llm.chat = AsyncMock(return_value=MagicMock(
            choices=[MagicMock(message=MagicMock(
                content="",
                tool_calls=[MagicMock(
                    id="tc1",
                    type="function",
                    function=MagicMock(name="read_file", arguments='{"file_path":"/test"}')
                )]
            ))],
            usage=MagicMock(total_tokens=10)
        ))
        
        callbacks = MagicMock()
        callbacks.is_cancelled.return_value = False
        
        registry = MagicMock()
        registry.get_schemas.return_value = []
        registry.execute.return_value = "file content"
        
        engine = AgentEngine(
            llm_provider=llm,
            tool_registry=registry,
            config=EngineConfig(permissions={"r"}),
            callbacks=callbacks,
        )
        
        async def _test():
            await engine.run([{"role": "system", "content": "sys"}])
        
        _run_async(_test())
        
        registry.execute.assert_called_once()

    def test_tool_start_complete_callbacks(self):
        """Engine must call on_tool_start and on_tool_complete."""
        pytest.importorskip("ayder_cli.application.agent_engine",
                           reason="Engine not yet implemented")
        from ayder_cli.application.agent_engine import AgentEngine, EngineConfig
        
        llm = MagicMock()
        llm.chat = AsyncMock(return_value=MagicMock(
            choices=[MagicMock(message=MagicMock(
                content="",
                tool_calls=[MagicMock(
                    id="tc1",
                    type="function",
                    function=MagicMock(name="read_file", arguments='{"file_path":"/test"}')
                )]
            ))],
            usage=MagicMock(total_tokens=10)
        ))
        
        callbacks = MagicMock()
        callbacks.is_cancelled.return_value = False
        
        registry = MagicMock()
        registry.get_schemas.return_value = []
        registry.execute.return_value = "file content"
        
        engine = AgentEngine(
            llm_provider=llm,
            tool_registry=registry,
            config=EngineConfig(permissions={"r"}),
            callbacks=callbacks,
        )
        
        async def _test():
            await engine.run([{"role": "system", "content": "sys"}])
        
        _run_async(_test())
        
        callbacks.on_tool_start.assert_called_once()
        callbacks.on_tool_complete.assert_called_once()


# ---------------------------------------------------------------------------
# Error Handling Integration Tests
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Contract: Engine handles errors gracefully."""

    def test_llm_error_reported(self):
        """LLM errors should be reported via callbacks."""
        pytest.importorskip("ayder_cli.application.agent_engine",
                           reason="Engine not yet implemented")
        from ayder_cli.application.agent_engine import AgentEngine, EngineConfig
        
        llm = MagicMock()
        llm.chat = AsyncMock(side_effect=ConnectionError("LLM unavailable"))
        
        callbacks = MagicMock()
        callbacks.is_cancelled.return_value = False
        
        engine = AgentEngine(
            llm_provider=llm,
            tool_registry=MagicMock(),
            config=EngineConfig(),
            callbacks=callbacks,
        )
        
        async def _test():
            await engine.run([{"role": "system", "content": "sys"}])
        
        _run_async(_test())
        
        # Error should be reported via system_message callback
        callbacks.on_system_message.assert_called()
        
        # Verify error message content
        error_calls = [
            call for call in callbacks.on_system_message.call_args_list
            if any("error" in str(arg).lower() or "unavailable" in str(arg).lower() 
                   for arg in call.args)
        ]
        
        # Must have at least one error-related system message
        assert len(error_calls) > 0, \
            "Error must be reported via on_system_message callback"

    def test_tool_error_handled(self):
        """Tool execution errors should be handled gracefully."""
        pytest.importorskip("ayder_cli.application.agent_engine",
                           reason="Engine not yet implemented")
        from ayder_cli.application.agent_engine import AgentEngine, EngineConfig
        
        llm = MagicMock()
        llm.chat = AsyncMock(return_value=MagicMock(
            choices=[MagicMock(message=MagicMock(
                content="",
                tool_calls=[MagicMock(
                    id="tc1",
                    type="function",
                    function=MagicMock(name="read_file", arguments='{"file_path":"/test"}')
                )]
            ))],
            usage=MagicMock(total_tokens=10)
        ))
        
        callbacks = MagicMock()
        callbacks.is_cancelled.return_value = False
        
        registry = MagicMock()
        registry.get_schemas.return_value = []
        registry.execute.side_effect = RuntimeError("Tool failed")
        
        engine = AgentEngine(
            llm_provider=llm,
            tool_registry=registry,
            config=EngineConfig(permissions={"r"}),
            callbacks=callbacks,
        )
        
        # Should not raise - errors should be caught and reported
        async def _test():
            await engine.run([{"role": "system", "content": "sys"}])
        
        try:
            _run_async(_test())
        except RuntimeError:
            pytest.fail("Tool errors must be handled gracefully, not propagated")


# ---------------------------------------------------------------------------
# Contract Summary
# ---------------------------------------------------------------------------


class TestIntegrationContractSummary:
    """Summary of integration contracts.
    
    Shared Async Engine must integrate with:
    
    1. CheckpointManager:
       - Accept checkpoint_manager parameter
       - Trigger checkpoint at max iterations
       - Restore from checkpoint and continue
    
    2. MemoryManager:
       - Accept memory_manager parameter
       - Create checkpoint via memory_manager
       - Restore via memory_manager
    
    3. Callbacks:
       - on_thinking_start/stop
       - on_iteration_update
       - on_token_usage
       - on_tool_start/complete
       - request_confirmation (async)
       - is_cancelled
    
    4. Tool Registry:
       - Execute tools through registry
       - Handle tool errors gracefully
    
    5. Error Handling:
       - LLM errors reported via callbacks
       - Tool errors don't crash engine
    """

    def test_integration_contracts_documented(self):
        """Documentation test."""
        pass
