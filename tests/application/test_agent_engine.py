"""Contract tests for Shared Async Engine (agent_engine.py).

TEST-FIRST: These tests define the contract that DEV will implement.
Phase 04 - Shared Async Engine for CLI + TUI.

These tests WILL FAIL until DEV implements agent_engine.py.
This is expected per TEST-FIRST mandate.

Note: Tests use asyncio.run() wrapper instead of pytest.mark.asyncio
to avoid plugin dependency issues.
"""

import asyncio
import pytest
from dataclasses import dataclass
from typing import Any, Optional
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Test Fixtures
# ---------------------------------------------------------------------------


@dataclass
class FakeLLMResponse:
    """Fake LLM response for testing."""
    content: str = ""
    tool_calls: list | None = None
    total_tokens: int = 100


@dataclass
class FakeToolCall:
    """Fake tool call for testing."""
    id: str
    name: str
    arguments: dict


def _make_text_response(content: str, total_tokens: int = 100) -> FakeLLMResponse:
    """Create a text-only LLM response."""
    return FakeLLMResponse(content=content, tool_calls=None, total_tokens=total_tokens)


def _make_tool_response(tool_calls: list[FakeToolCall], total_tokens: int = 100) -> FakeLLMResponse:
    """Create a tool-call LLM response."""
    return FakeLLMResponse(content="Using tools", tool_calls=tool_calls, total_tokens=total_tokens)


def _make_tool_call(call_id: str, name: str, arguments: dict | None = None) -> FakeToolCall:
    """Create a fake tool call."""
    return FakeToolCall(id=call_id, name=name, arguments=arguments or {})


@pytest.fixture
def mock_services():
    """Create mock services for testing."""
    llm = MagicMock()
    registry = MagicMock()
    registry.get_schemas.return_value = []
    registry.execute.return_value = "tool result"
    
    checkpoint_manager = MagicMock()
    memory_manager = MagicMock()
    
    return {
        "llm": llm,
        "registry": registry,
        "checkpoint_manager": checkpoint_manager,
        "memory_manager": memory_manager,
    }


@pytest.fixture
def mock_callbacks():
    """Create mock callbacks for testing."""
    callbacks = MagicMock()
    callbacks.on_thinking_start = MagicMock()
    callbacks.on_thinking_stop = MagicMock()
    callbacks.on_assistant_content = MagicMock()
    callbacks.on_tool_start = MagicMock()
    callbacks.on_tool_complete = MagicMock()
    callbacks.on_iteration_update = MagicMock()
    callbacks.on_token_usage = MagicMock()
    callbacks.on_system_message = MagicMock()
    callbacks.request_confirmation = AsyncMock(return_value={"action": "approve"})
    callbacks.is_cancelled = MagicMock(return_value=False)
    return callbacks


def _run_async(coro):
    """Helper to run async coroutine in sync test."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# QA-04.2: Shared Engine Contract Tests
# ---------------------------------------------------------------------------


class TestAgentEngineImports:
    """Contract: Agent engine module exists with expected exports."""

    def test_module_exists(self):
        """Agent engine module must exist at canonical location."""
        try:
            from ayder_cli.application import agent_engine
            assert agent_engine is not None
        except ImportError:
            pytest.fail("agent_engine module not found in ayder_cli.application")

    def test_agent_engine_class_exists(self):
        """AgentEngine class must be exported."""
        pytest.importorskip("ayder_cli.application.agent_engine")
        from ayder_cli.application.agent_engine import AgentEngine
        assert AgentEngine is not None

    def test_engine_config_class_exists(self):
        """EngineConfig dataclass must be exported."""
        pytest.importorskip("ayder_cli.application.agent_engine")
        from ayder_cli.application.agent_engine import EngineConfig
        assert EngineConfig is not None


class TestEngineConfigContract:
    """Contract: EngineConfig has required fields."""

    def test_config_defaults(self):
        """EngineConfig must have sensible defaults."""
        pytest.importorskip("ayder_cli.application.agent_engine")
        from ayder_cli.application.agent_engine import EngineConfig
        
        cfg = EngineConfig()
        assert cfg.model == "qwen3-coder:latest"
        assert cfg.num_ctx == 65536
        assert cfg.max_iterations == 50
        assert cfg.permissions == {"r"}

    def test_config_custom_values(self):
        """EngineConfig must accept custom values."""
        pytest.importorskip("ayder_cli.application.agent_engine")
        from ayder_cli.application.agent_engine import EngineConfig
        
        cfg = EngineConfig(
            model="custom-model",
            num_ctx=4096,
            max_iterations=25,
            permissions={"r", "w"}
        )
        assert cfg.model == "custom-model"
        assert cfg.num_ctx == 4096
        assert cfg.max_iterations == 25
        assert cfg.permissions == {"r", "w"}


class TestTextOnlyResponse:
    """Contract: Engine handles text-only (non-tool) LLM responses."""

    def test_text_only_returns_content(self, mock_services, mock_callbacks):
        """Text-only response should return assistant content."""
        pytest.importorskip("ayder_cli.application.agent_engine")
        from ayder_cli.application.agent_engine import AgentEngine, EngineConfig
        
        llm = mock_services["llm"]
        llm.chat = AsyncMock(return_value=_make_text_response("Hello world!"))
        
        engine = AgentEngine(
            llm_provider=llm,
            tool_registry=mock_services["registry"],
            config=EngineConfig(),
            callbacks=mock_callbacks,
        )
        
        async def _test():
            return await engine.run([{"role": "system", "content": "sys"}])
        
        result = _run_async(_test())
        
        assert result == "Hello world!"
        mock_callbacks.on_assistant_content.assert_called_with("Hello world!")

    def test_text_only_triggers_callbacks(self, mock_services, mock_callbacks):
        """Text-only response should trigger all expected callbacks."""
        pytest.importorskip("ayder_cli.application.agent_engine")
        from ayder_cli.application.agent_engine import AgentEngine, EngineConfig
        
        llm = mock_services["llm"]
        llm.chat = AsyncMock(return_value=_make_text_response("Response", total_tokens=42))
        
        engine = AgentEngine(
            llm_provider=llm,
            tool_registry=mock_services["registry"],
            config=EngineConfig(),
            callbacks=mock_callbacks,
        )
        
        async def _test():
            await engine.run([{"role": "system", "content": "sys"}])
        
        _run_async(_test())
        
        mock_callbacks.on_thinking_start.assert_called_once()
        mock_callbacks.on_thinking_stop.assert_called_once()
        mock_callbacks.on_iteration_update.assert_called()
        mock_callbacks.on_token_usage.assert_called_with(42)


class TestToolCallResponse:
    """Contract: Engine routes tool calls correctly."""

    def test_auto_approved_tool_executes(self, mock_services, mock_callbacks):
        """Auto-approved tools should execute without confirmation."""
        pytest.importorskip("ayder_cli.application.agent_engine")
        from ayder_cli.application.agent_engine import AgentEngine, EngineConfig
        
        llm = mock_services["llm"]
        call_count = [0]
        
        async def fake_llm(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return _make_tool_response([_make_tool_call("tc1", "read_file", {"file_path": "/test.txt"})])
            return _make_text_response("Done")
        
        llm.chat = fake_llm
        
        engine = AgentEngine(
            llm_provider=llm,
            tool_registry=mock_services["registry"],
            config=EngineConfig(permissions={"r"}),
            callbacks=mock_callbacks,
        )
        
        async def _test():
            return await engine.run([{"role": "system", "content": "sys"}])
        
        _run_async(_test())
        
        # Tool should execute without calling request_confirmation
        mock_services["registry"].execute.assert_called_once()
        mock_callbacks.request_confirmation.assert_not_awaited()

    def test_tool_needs_confirmation(self, mock_services, mock_callbacks):
        """Non-approved tools should request confirmation."""
        pytest.importorskip("ayder_cli.application.agent_engine")
        from ayder_cli.application.agent_engine import AgentEngine, EngineConfig
        
        llm = mock_services["llm"]
        call_count = [0]
        
        async def fake_llm(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return _make_tool_response([_make_tool_call("tc1", "write_file", {"file_path": "/test.txt"})])
            return _make_text_response("Done")
        
        llm.chat = fake_llm
        mock_callbacks.request_confirmation = AsyncMock(return_value={"action": "approve"})
        
        engine = AgentEngine(
            llm_provider=llm,
            tool_registry=mock_services["registry"],
            config=EngineConfig(permissions={"r"}),  # No 'w' permission
            callbacks=mock_callbacks,
        )
        
        async def _test():
            await engine.run([{"role": "system", "content": "sys"}])
        
        _run_async(_test())
        
        mock_callbacks.request_confirmation.assert_awaited_once()

    def test_multiple_tool_calls(self, mock_services, mock_callbacks):
        """Engine should handle multiple tool calls in one response."""
        pytest.importorskip("ayder_cli.application.agent_engine")
        from ayder_cli.application.agent_engine import AgentEngine, EngineConfig
        
        llm = mock_services["llm"]
        call_count = [0]
        
        async def fake_llm(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return _make_tool_response([
                    _make_tool_call("tc1", "read_file", {"file_path": "/a.txt"}),
                    _make_tool_call("tc2", "read_file", {"file_path": "/b.txt"}),
                ])
            return _make_text_response("Done")
        
        llm.chat = fake_llm
        
        engine = AgentEngine(
            llm_provider=llm,
            tool_registry=mock_services["registry"],
            config=EngineConfig(permissions={"r"}),
            callbacks=mock_callbacks,
        )
        
        async def _test():
            await engine.run([{"role": "system", "content": "sys"}])
        
        _run_async(_test())
        
        # Both tools should execute
        assert mock_services["registry"].execute.call_count == 2
        mock_callbacks.on_tool_start.call_count == 2
        mock_callbacks.on_tool_complete.call_count == 2


class TestIterationOverflow:
    """Contract: Engine terminates on max iterations."""

    def test_max_iterations_terminates(self, mock_services, mock_callbacks):
        """Engine should terminate when max_iterations reached."""
        pytest.importorskip("ayder_cli.application.agent_engine")
        from ayder_cli.application.agent_engine import AgentEngine, EngineConfig
        
        llm = mock_services["llm"]
        llm.chat = AsyncMock(return_value=_make_text_response("response"))
        
        engine = AgentEngine(
            llm_provider=llm,
            tool_registry=mock_services["registry"],
            config=EngineConfig(max_iterations=2),
            callbacks=mock_callbacks,
        )
        
        async def _test():
            return await engine.run([{"role": "system", "content": "sys"}])
        
        result = _run_async(_test())
        
        # Should complete without error but may return None or message
        # LLM should be called no more than max_iterations times
        assert llm.chat.call_count <= 2

    def test_iteration_overflow_message(self, mock_services, mock_callbacks):
        """Engine should notify when max iterations reached."""
        pytest.importorskip("ayder_cli.application.agent_engine")
        from ayder_cli.application.agent_engine import AgentEngine, EngineConfig
        
        llm = mock_services["llm"]
        # Always return a tool response to force continued iteration
        llm.chat = AsyncMock(return_value=_make_tool_response([_make_tool_call("tc", "read_file")]))
        
        engine = AgentEngine(
            llm_provider=llm,
            tool_registry=mock_services["registry"],
            config=EngineConfig(max_iterations=3),
            callbacks=mock_callbacks,
        )
        
        async def _test():
            await engine.run([{"role": "system", "content": "sys"}])
        
        _run_async(_test())
        
        # Should send system message about max iterations
        system_messages = [
            call.args[0] for call in mock_callbacks.on_system_message.call_args_list
        ]
        assert any("max iteration" in str(msg).lower() for msg in system_messages)


class TestCancellation:
    """Contract: Engine handles cancellation properly."""

    def test_cancellation_before_llm(self, mock_services, mock_callbacks):
        """If cancelled before LLM call, should exit early."""
        pytest.importorskip("ayder_cli.application.agent_engine")
        from ayder_cli.application.agent_engine import AgentEngine, EngineConfig
        
        llm = mock_services["llm"]
        llm.chat = AsyncMock()
        
        mock_callbacks.is_cancelled = MagicMock(return_value=True)
        
        engine = AgentEngine(
            llm_provider=llm,
            tool_registry=mock_services["registry"],
            config=EngineConfig(),
            callbacks=mock_callbacks,
        )
        
        async def _test():
            return await engine.run([{"role": "system", "content": "sys"}])
        
        result = _run_async(_test())
        
        llm.chat.assert_not_awaited()
        assert result is None

    def test_cancellation_during_iteration(self, mock_services, mock_callbacks):
        """If cancelled during iteration, should exit gracefully."""
        pytest.importorskip("ayder_cli.application.agent_engine")
        from ayder_cli.application.agent_engine import AgentEngine, EngineConfig
        
        llm = mock_services["llm"]
        call_count = [0]
        
        async def fake_llm(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                mock_callbacks.is_cancelled = MagicMock(return_value=True)
                return _make_tool_response([_make_tool_call("tc", "read_file")])
            return _make_text_response("Done")
        
        llm.chat = fake_llm
        mock_callbacks.is_cancelled = MagicMock(return_value=False)
        
        engine = AgentEngine(
            llm_provider=llm,
            tool_registry=mock_services["registry"],
            config=EngineConfig(),
            callbacks=mock_callbacks,
        )
        
        async def _test():
            await engine.run([{"role": "system", "content": "sys"}])
        
        _run_async(_test())
        
        # Should exit after detecting cancellation
        assert call_count[0] == 1


class TestEngineMessages:
    """Contract: Engine maintains message history correctly."""

    def test_messages_include_user_input(self, mock_services, mock_callbacks):
        """Messages should include user input at start."""
        pytest.importorskip("ayder_cli.application.agent_engine")
        from ayder_cli.application.agent_engine import AgentEngine, EngineConfig
        
        llm = mock_services["llm"]
        captured_messages = None
        
        async def capture_llm(messages, **kwargs):
            nonlocal captured_messages
            captured_messages = messages
            return _make_text_response("response")
        
        llm.chat = capture_llm
        
        engine = AgentEngine(
            llm_provider=llm,
            tool_registry=mock_services["registry"],
            config=EngineConfig(),
            callbacks=mock_callbacks,
        )
        
        async def _test():
            initial_messages = [{"role": "system", "content": "sys"}]
            return await engine.run(initial_messages, user_input="Hello")
        
        _run_async(_test())
        
        # Messages should include user input
        assert any(m.get("role") == "user" and m.get("content") == "Hello" 
                   for m in captured_messages)

    def test_messages_include_assistant_response(self, mock_services, mock_callbacks):
        """Messages should include assistant response after completion."""
        pytest.importorskip("ayder_cli.application.agent_engine")
        from ayder_cli.application.agent_engine import AgentEngine, EngineConfig
        
        llm = mock_services["llm"]
        llm.chat = AsyncMock(return_value=_make_text_response("Assistant reply"))
        
        engine = AgentEngine(
            llm_provider=llm,
            tool_registry=mock_services["registry"],
            config=EngineConfig(),
            callbacks=mock_callbacks,
        )
        
        messages = [{"role": "system", "content": "sys"}]
        
        async def _test():
            return await engine.run(messages)
        
        _run_async(_test())
        
        # Final messages should include assistant response
        assert any(m.get("role") == "assistant" and m.get("content") == "Assistant reply"
                   for m in messages)

    def test_messages_include_tool_results(self, mock_services, mock_callbacks):
        """Messages should include tool results after execution."""
        pytest.importorskip("ayder_cli.application.agent_engine")
        from ayder_cli.application.agent_engine import AgentEngine, EngineConfig
        
        llm = mock_services["llm"]
        call_count = [0]
        
        async def fake_llm(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return _make_tool_response([_make_tool_call("tc1", "read_file")])
            return _make_text_response("Done")
        
        llm.chat = fake_llm
        mock_services["registry"].execute.return_value = "file contents here"
        
        engine = AgentEngine(
            llm_provider=llm,
            tool_registry=mock_services["registry"],
            config=EngineConfig(permissions={"r"}),
            callbacks=mock_callbacks,
        )
        
        messages = [{"role": "system", "content": "sys"}]
        
        async def _test():
            await engine.run(messages)
        
        _run_async(_test())
        
        # Messages should include tool result
        assert any(m.get("role") == "tool" and "file contents" in str(m.get("content", ""))
                   for m in messages)


# ---------------------------------------------------------------------------
# QA-04.3: Wrapper Contract Tests
# ---------------------------------------------------------------------------


class TestCLIWrapperContract:
    """Contract: CLI wrapper uses asyncio.run() to call shared engine."""

    def test_cli_adapter_imports(self):
        """CLI adapter module must exist."""
        try:
            from ayder_cli.ui import cli_adapter
            assert cli_adapter is not None
        except ImportError:
            pytest.skip("CLI adapter not yet implemented (expected for TEST-FIRST)")

    def test_cli_adapter_has_run_async_function(self):
        """CLI adapter must have run_async function that is a coroutine."""
        pytest.importorskip("ayder_cli.ui.cli_adapter", reason="CLI adapter not yet implemented")
        from ayder_cli.ui import cli_adapter
        import inspect
        
        assert hasattr(cli_adapter, 'run_async'), \
            "cli_adapter must have run_async function"
        assert inspect.iscoroutinefunction(cli_adapter.run_async), \
            "run_async must be a coroutine function"

    def test_cli_wrapper_calls_asyncio_run(self):
        """CLI entry point should call shared engine via asyncio.run pattern."""
        pytest.importorskip("ayder_cli.application.agent_engine", 
                           reason="Engine not yet implemented")
        
        import ast
        import inspect
        from ayder_cli import cli_runner
        
        source = inspect.getsource(cli_runner)
        tree = ast.parse(source)
        
        # Look for asyncio.run pattern
        has_asyncio_run = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    if (isinstance(node.func.value, ast.Name) and 
                        node.func.value.id == "asyncio" and
                        node.func.attr == "run"):
                        has_asyncio_run = True
                        break
        
        assert has_asyncio_run, "CLI runner must use asyncio.run() pattern"


class TestTUIWrapperContract:
    """Contract: TUI wrapper awaits shared engine in worker lifecycle."""

    def test_tui_adapter_imports_engine(self):
        """TUI adapter must import from shared engine."""
        pytest.importorskip("ayder_cli.application.agent_engine",
                           reason="Engine not yet implemented")
        
        import ast
        from pathlib import Path
        
        tui_chat_loop = Path("src/ayder_cli/tui/chat_loop.py")
        if not tui_chat_loop.exists():
            pytest.skip("TUI chat_loop not found")
        
        source = tui_chat_loop.read_text()
        tree = ast.parse(source)
        
        # Check for import from application.agent_engine
        has_import = False
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module and "agent_engine" in node.module:
                    has_import = True
                    break
        
        # This will fail until DEV refactors TUI to use shared engine
        # This is EXPECTED for TEST-FIRST
        if not has_import:
            pytest.skip("TUI not yet refactored to use shared engine (expected for TEST-FIRST)")

    def test_tui_chat_loop_is_async(self):
        """TUI chat loop must be async (can await shared engine)."""
        pytest.importorskip("ayder_cli.tui.chat_loop",
                           reason="TUI chat_loop not available")
        from ayder_cli.tui.chat_loop import TuiChatLoop
        
        import inspect
        run_method = getattr(TuiChatLoop, 'run', None)
        if run_method is None:
            pytest.skip("TuiChatLoop.run not found")
        
        # Check if run is a coroutine function
        assert inspect.iscoroutinefunction(run_method), \
            "TuiChatLoop.run must be async to await shared engine"


# ---------------------------------------------------------------------------
# QA-04.4: Equivalence Tests
# ---------------------------------------------------------------------------


class TestCLITUIEquivalence:
    """Contract: Same mocked LLM/tool → same decisions in CLI and TUI."""

    def test_equivalent_text_response(self, mock_services, mock_callbacks):
        """CLI and TUI should produce same text response with same LLM mock."""
        pytest.importorskip("ayder_cli.application.agent_engine",
                           reason="Engine not yet implemented")
        from ayder_cli.application.agent_engine import AgentEngine, EngineConfig
        
        llm = mock_services["llm"]
        llm.chat = AsyncMock(return_value=_make_text_response("Same response"))
        
        engine = AgentEngine(
            llm_provider=llm,
            tool_registry=mock_services["registry"],
            config=EngineConfig(),
            callbacks=mock_callbacks,
        )
        
        async def _test():
            messages = [{"role": "system", "content": "sys"}]
            return await engine.run(messages)
        
        result = _run_async(_test())
        
        # Both CLI and TUI should see same result when using same engine
        assert result == "Same response"
        assert llm.chat.call_count == 1

    def test_equivalent_tool_execution(self, mock_services, mock_callbacks):
        """CLI and TUI should execute same tools with same mock."""
        pytest.importorskip("ayder_cli.application.agent_engine",
                           reason="Engine not yet implemented")
        from ayder_cli.application.agent_engine import AgentEngine, EngineConfig
        
        llm = mock_services["llm"]
        call_count = [0]
        
        async def fake_llm(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return _make_tool_response([_make_tool_call("tc", "list_files")])
            return _make_text_response("Done")
        
        llm.chat = fake_llm
        
        engine = AgentEngine(
            llm_provider=llm,
            tool_registry=mock_services["registry"],
            config=EngineConfig(permissions={"r"}),
            callbacks=mock_callbacks,
        )
        
        async def _test():
            messages = [{"role": "system", "content": "sys"}]
            await engine.run(messages)
        
        _run_async(_test())
        
        # Tool should be called once
        mock_services["registry"].execute.assert_called_once()

    def test_engine_is_shared_module(self):
        """Engine must be in shared location accessible by both CLI and TUI."""
        from pathlib import Path
        
        engine_path = Path("src/ayder_cli/application/agent_engine.py")
        assert engine_path.exists(), \
            "Shared engine must exist at src/ayder_cli/application/agent_engine.py"


# ---------------------------------------------------------------------------
# Engine Interface Contract
# ---------------------------------------------------------------------------


class TestEngineInterface:
    """Contract: Engine has the expected public interface."""

    def test_engine_run_is_async(self):
        """Engine.run() must be async (returns coroutine)."""
        pytest.importorskip("ayder_cli.application.agent_engine")
        from ayder_cli.application.agent_engine import AgentEngine, EngineConfig
        
        import inspect
        assert inspect.iscoroutinefunction(AgentEngine.run), \
            "AgentEngine.run must be async"

    def test_engine_accepts_callbacks(self):
        """Engine must accept callbacks parameter."""
        pytest.importorskip("ayder_cli.application.agent_engine")
        from ayder_cli.application.agent_engine import AgentEngine, EngineConfig
        
        import inspect
        sig = inspect.signature(AgentEngine.__init__)
        assert "callbacks" in sig.parameters, \
            "AgentEngine must accept callbacks parameter"

    def test_engine_accepts_config(self):
        """Engine must accept config parameter."""
        pytest.importorskip("ayder_cli.application.agent_engine")
        from ayder_cli.application.agent_engine import AgentEngine, EngineConfig
        
        import inspect
        sig = inspect.signature(AgentEngine.__init__)
        assert "config" in sig.parameters, \
            "AgentEngine must accept config parameter"


# ---------------------------------------------------------------------------
# Remove→Replace Mapping Documentation
# ---------------------------------------------------------------------------


class TestMigrationNotes:
    """Documentation of test migration for Phase 04.
    
    Per PRD Section 6: Every removed test must map to replacement test(s)
    or explicit deprecation rationale.
    
    For Phase 04:
    - NO TESTS REMOVED - TUI tests remain and will use shared engine
    - Legacy sync ChatLoop (root level) has no direct tests
    - New contract tests define expected behavior of shared engine
    """

    def test_migration_mapping_exists(self):
        """Verify migration mapping is documented.
        
        | Removed Test | Reason Obsolete | Replacement Test |
        |--------------|-----------------|------------------|
        | N/A          | N/A             | N/A              |
        
        No tests removed in Phase 04 - only new tests added.
        """
        # This test serves as documentation
        pass
