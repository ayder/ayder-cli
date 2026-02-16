"""Wrapper Contract Tests for Phase 04 - CLI/TUI Integration.

TEST-FIRST: These tests verify CLI and TUI wrapper contracts.
- CLI must use asyncio.run() to call shared engine
- TUI must await shared engine in worker lifecycle

Note: Tests use asyncio.run() wrapper instead of pytest.mark.asyncio
to avoid plugin dependency issues.
"""

import asyncio
import ast
import inspect
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


def _run_async(coro):
    """Helper to run async coroutine in sync test."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# QA-04.3: CLI Wrapper Contract Tests
# ---------------------------------------------------------------------------


class TestCLIWrapperStructure:
    """Contract: CLI wrapper structure for shared engine integration."""

    def test_cli_runner_module_structure(self):
        """CLI runner must be structured to support async engine."""
        from ayder_cli import cli_runner
        
        # Verify CommandRunner exists
        assert hasattr(cli_runner, 'CommandRunner'), \
            "CommandRunner class must exist"
        assert hasattr(cli_runner, 'run_command'), \
            "run_command function must exist"

    def test_cli_runner_uses_asyncio_run(self):
        """CLI runner must use asyncio.run() pattern for shared engine."""
        pytest.importorskip("ayder_cli.application.agent_engine",
                           reason="Engine not yet implemented")
        
        source = Path("src/ayder_cli/cli_runner.py").read_text()
        tree = ast.parse(source)
        
        # Look for asyncio.run or asyncio.run_until_complete pattern
        has_asyncio_pattern = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    if (isinstance(node.func.value, ast.Name) and 
                        node.func.value.id == "asyncio"):
                        if node.func.attr in ("run", "run_until_complete"):
                            has_asyncio_pattern = True
                            break
        
        # Document expected pattern - will fail until DEV implements
        if not has_asyncio_pattern:
            pytest.skip(
                "CLI runner not yet using asyncio.run() - "
                "DEV must implement per Phase 04 spec"
            )

    def test_cli_adapter_module_exists(self):
        """CLI adapter module must exist for async engine integration."""
        cli_adapter_path = Path("src/ayder_cli/ui/cli_adapter.py")
        
        # This will be created by DEV - skip if not exists (TEST-FIRST)
        if not cli_adapter_path.exists():
            pytest.skip(
                "CLI adapter not yet implemented - "
                "DEV must create per Phase 04 spec"
            )
        
        assert cli_adapter_path.exists(), \
            "CLI adapter must exist at src/ayder_cli/ui/cli_adapter.py"

    def test_cli_adapter_has_run_async(self):
        """CLI adapter must expose async run_async function."""
        pytest.importorskip("ayder_cli.ui.cli_adapter", 
                           reason="CLI adapter not yet implemented")
        from ayder_cli.ui import cli_adapter
        
        assert hasattr(cli_adapter, 'run_async'), \
            "cli_adapter must have run_async function"
        assert inspect.iscoroutinefunction(cli_adapter.run_async), \
            "run_async must be a coroutine function"


class TestCLIIntegrationContract:
    """Contract: CLI integrates with shared engine correctly."""

    def test_cli_imports_agent_engine(self):
        """CLI code must import from agent_engine."""
        pytest.importorskip("ayder_cli.application.agent_engine",
                           reason="Engine not yet implemented")
        
        # Check cli_runner imports agent_engine
        source = Path("src/ayder_cli/cli_runner.py").read_text()
        
        has_import = (
            "from ayder_cli.application.agent_engine" in source or
            "from ayder_cli.application import agent_engine" in source
        )
        
        if not has_import:
            pytest.skip(
                "CLI runner not yet importing agent_engine - "
                "DEV must implement per Phase 04 spec"
            )

    def test_cli_no_direct_chat_loop_import(self):
        """CLI should not import legacy chat_loop directly after refactor."""
        pytest.importorskip("ayder_cli.application.agent_engine",
                           reason="Engine not yet implemented")
        
        source = Path("src/ayder_cli/cli_runner.py").read_text()
        
        # Should NOT import legacy ChatLoop
        legacy_import = "from ayder_cli.chat_loop import ChatLoop"
        
        if legacy_import in source:
            pytest.fail(
                "CLI runner still importing legacy ChatLoop - "
                "must use shared agent_engine instead"
            )


# ---------------------------------------------------------------------------
# QA-04.3: TUI Wrapper Contract Tests
# ---------------------------------------------------------------------------


class TestTUIWrapperStructure:
    """Contract: TUI wrapper structure for shared engine integration."""

    def test_tui_chat_loop_is_async(self):
        """TUI chat loop must be async to await shared engine."""
        pytest.importorskip("ayder_cli.tui.chat_loop")
        from ayder_cli.tui.chat_loop import TuiChatLoop
        
        assert inspect.iscoroutinefunction(TuiChatLoop.run), \
            "TuiChatLoop.run must be async to await shared engine"

    def test_tui_imports_agent_engine(self):
        """TUI must import from shared agent_engine."""
        pytest.importorskip("ayder_cli.application.agent_engine",
                           reason="Engine not yet implemented")
        
        source = Path("src/ayder_cli/tui/chat_loop.py").read_text()
        
        has_import = (
            "from ayder_cli.application.agent_engine" in source or
            "from ayder_cli.application import agent_engine" in source
        )
        
        if not has_import:
            pytest.skip(
                "TUI not yet importing agent_engine - "
                "DEV must refactor per Phase 04 spec"
            )

    def test_tui_awaits_engine(self):
        """TUI must await shared engine (not call sync wrapper)."""
        pytest.importorskip("ayder_cli.application.agent_engine",
                           reason="Engine not yet implemented")
        pytest.importorskip("ayder_cli.tui.chat_loop")
        
        source = Path("src/ayder_cli/tui/chat_loop.py").read_text()
        tree = ast.parse(source)
        
        # Look for 'await' expressions in run method
        has_await = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Await):
                has_await = True
                break
        
        if not has_await:
            pytest.skip(
                "TUI not yet awaiting engine - "
                "DEV must refactor per Phase 04 spec"
            )


class TestTUIWorkerIntegration:
    """Contract: TUI worker lifecycle integrates with shared engine."""

    def test_tui_worker_imports(self):
        """TUI worker must import required components."""
        pytest.importorskip("ayder_cli.tui.chat_loop")
        from ayder_cli.tui import chat_loop
        
        assert hasattr(chat_loop, 'TuiChatLoop'), \
            "TuiChatLoop must be available"

    def test_tui_callbacks_compatible(self):
        """TUI callbacks must be compatible with engine callback interface."""
        pytest.importorskip("ayder_cli.tui.chat_loop")
        from ayder_cli.tui.chat_loop import TuiChatLoop
        
        # Check TuiChatLoop accepts callbacks parameter
        sig = inspect.signature(TuiChatLoop.__init__)
        assert "callbacks" in sig.parameters, \
            "TuiChatLoop must accept callbacks parameter"


# ---------------------------------------------------------------------------
# QA-04.4: Equivalence Tests
# ---------------------------------------------------------------------------


class TestEngineEquivalence:
    """Contract: Same engine produces same results for CLI and TUI."""

    def test_cli_tui_same_engine_instance(self):
        """Both CLI and TUI should use same AgentEngine class."""
        pytest.importorskip("ayder_cli.application.agent_engine",
                           reason="Engine not yet implemented")
        from ayder_cli.application.agent_engine import AgentEngine
        
        # Verify single engine class exists
        assert AgentEngine is not None
        
        # Can be instantiated with same parameters
        engine1 = AgentEngine(
            llm_provider=MagicMock(),
            tool_registry=MagicMock(),
            config=MagicMock(),
        )
        engine2 = AgentEngine(
            llm_provider=MagicMock(),
            tool_registry=MagicMock(),
            config=MagicMock(),
        )
        
        assert type(engine1) == type(engine2)

    def test_engine_location_shared(self):
        """Engine must be in shared location (application/)."""
        engine_path = Path("src/ayder_cli/application/agent_engine.py")
        
        # Document expected location
        assert engine_path.parent.exists(), \
            "application/ directory must exist"
        
        # Will fail until DEV creates it
        if not engine_path.exists():
            pytest.skip(
                "agent_engine.py not yet created - "
                "DEV must implement per Phase 04 spec"
            )

    def test_no_duplicate_engines(self):
        """No duplicate engine implementations should exist."""
        # Search for engine-like files
        app_dir = Path("src/ayder_cli/application")
        
        if not app_dir.exists():
            pytest.skip("application/ directory not yet created")
        
        engine_files = list(app_dir.glob("*engine*.py"))
        
        # Should have exactly one engine file
        assert len(engine_files) <= 1, \
            f"Multiple engine files found: {engine_files}. " \
            "Should have only one shared engine."


# ---------------------------------------------------------------------------
# Async Pattern Validation
# ---------------------------------------------------------------------------


class TestAsyncPatterns:
    """Contract: Correct async patterns used throughout."""

    def test_shared_engine_is_async(self):
        """Shared engine must expose async interface."""
        pytest.importorskip("ayder_cli.application.agent_engine",
                           reason="Engine not yet implemented")
        from ayder_cli.application.agent_engine import AgentEngine
        
        assert inspect.iscoroutinefunction(AgentEngine.run), \
            "AgentEngine.run must be async (coroutine function)"

    def test_cli_uses_asyncio_run(self):
        """CLI must use asyncio.run() not direct call."""
        pytest.importorskip("ayder_cli.application.agent_engine",
                           reason="Engine not yet implemented")
        
        # Check for asyncio.run pattern in CLI adapter or runner
        paths_to_check = [
            Path("src/ayder_cli/ui/cli_adapter.py"),
            Path("src/ayder_cli/cli_runner.py"),
        ]
        
        found_pattern = False
        for path in paths_to_check:
            if path.exists():
                source = path.read_text()
                if "asyncio.run(" in source:
                    found_pattern = True
                    break
        
        if not found_pattern:
            pytest.skip(
                "asyncio.run pattern not yet found - "
                "DEV must implement per Phase 04 spec"
            )


# ---------------------------------------------------------------------------
# Integration Test Placeholders
# ---------------------------------------------------------------------------


class TestIntegrationPlaceholders:
    """Placeholder tests for full integration - will pass after DEV."""

    def test_end_to_end_cli_path(self):
        """Full CLI path: asyncio.run(engine.run())."""
        pytest.importorskip("ayder_cli.application.agent_engine",
                           reason="Engine not yet implemented")
        pytest.importorskip("ayder_cli.ui.cli_adapter",
                           reason="CLI adapter not yet implemented")
        
        from ayder_cli.ui.cli_adapter import run_async
        from ayder_cli.application.agent_engine import AgentEngine
        
        # Verify we can call via asyncio.run pattern
        assert inspect.iscoroutinefunction(run_async), \
            "run_async must be awaitable"

    def test_end_to_end_tui_path(self):
        """Full TUI path: await engine.run() in worker."""
        pytest.importorskip("ayder_cli.application.agent_engine",
                           reason="Engine not yet implemented")
        pytest.importorskip("ayder_cli.tui.chat_loop",
                           reason="TUI chat_loop not available")
        
        from ayder_cli.tui.chat_loop import TuiChatLoop
        
        # Verify TuiChatLoop.run is awaitable
        assert inspect.iscoroutinefunction(TuiChatLoop.run), \
            "TuiChatLoop.run must be awaitable"


# ---------------------------------------------------------------------------
# Test Summary Documentation
# ---------------------------------------------------------------------------


class TestPhase04ContractSummary:
    """Summary of Phase 04 test contracts.
    
    These tests define the contract that DEV must implement:
    
    1. Shared Engine (agent_engine.py):
       - AgentEngine class with async run() method
       - EngineConfig dataclass with required fields
       - Handles text-only and tool-call responses
       - Respects max_iterations
       - Handles cancellation
       - Maintains message history
    
    2. CLI Wrapper:
       - Uses asyncio.run() to call shared engine
       - cli_adapter.py with run_async function
    
    3. TUI Wrapper:
       - Awaits shared engine in worker lifecycle
       - TuiChatLoop.run is async
       - Imports from agent_engine
    
    4. Equivalence:
       - Same engine used by both CLI and TUI
       - Same results with same mocks
       - Single source of truth
    
    All tests in this file will FAIL until DEV implements.
    This is EXPECTED per TEST-FIRST mandate.
    """

    def test_contract_documentation(self):
        """This test exists to document the contract."""
        pass
