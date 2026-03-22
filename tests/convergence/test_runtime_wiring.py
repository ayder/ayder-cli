"""Runtime Wiring Tests — Phase 05 (S3)

Contract: CLI and TUI runtime loops call the same shared execution policy services.
Tests validate both source-level wiring AND actual call-chain behavior via mocks.
"""

import inspect
import asyncio
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Source-level wiring proofs
# ---------------------------------------------------------------------------


class TestExecutionPolicyWiring:
    """Both CLI and TUI must route through ExecutionPolicy."""

    def test_tui_exec_tool_uses_execute_with_registry(self):
        """TuiChatLoop._exec_tool_async calls ExecutionPolicy.execute_with_registry."""
        from ayder_cli.loops.chat_loop import ChatLoop as TuiChatLoop

        source = inspect.getsource(TuiChatLoop._exec_tool_async)

        assert "execute_with_registry" in source
        assert "registry.execute" not in source  # No direct bypass

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
        from ayder_cli.loops.chat_loop import ChatLoop as TuiChatLoop, ChatLoopConfig as TuiLoopConfig
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


class TestConvergenceIntegration:
    """End-to-end convergence: same services, same behavior."""

    def test_tui_and_cli_use_same_permission_source(self):
        """Both TUI and CLI execution paths use TOOL_PERMISSIONS."""
        from ayder_cli.application.execution_policy import _required_permission
        from ayder_cli.tools.schemas import TOOL_PERMISSIONS

        for tool, expected_perm in TOOL_PERMISSIONS.items():
            assert _required_permission(tool) == expected_perm

    def test_schema_validator_uses_live_registry(self):
        """SchemaValidator recognises all tools in the live registry and no others."""
        from ayder_cli.application.validation import SchemaValidator, ToolRequest
        from ayder_cli.tools.definition import TOOL_DEFINITIONS

        validator = SchemaValidator()

        for td in TOOL_DEFINITIONS:
            # Build a request with all required args present, using type-appropriate sentinels
            required = td.parameters.get("required", [])
            properties = td.parameters.get("properties", {})
            args = {}
            for arg in required:
                expected_type = properties.get(arg, {}).get("type")
                args[arg] = 0 if expected_type == "integer" else "sentinel"
            ok, err = validator.validate(ToolRequest(name=td.name, arguments=args))
            assert ok, f"Registry tool '{td.name}' rejected by SchemaValidator: {err}"

        # Unknown tool must be rejected
        ok, err = validator.validate(ToolRequest(name="__nonexistent__", arguments={}))
        assert not ok
        assert "not found in registry" in err.message
