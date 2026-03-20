"""Tests for the call_agent tool definition and handler."""

from unittest.mock import MagicMock

from ayder_cli.agents.tool import AGENT_TOOL_DEFINITION, create_call_agent_handler
from ayder_cli.tools.definition import ToolDefinition


class TestAgentToolDefinition:
    def test_definition_is_tool_definition(self):
        assert isinstance(AGENT_TOOL_DEFINITION, ToolDefinition)

    def test_definition_name(self):
        assert AGENT_TOOL_DEFINITION.name == "call_agent"

    def test_definition_parameters(self):
        params = AGENT_TOOL_DEFINITION.parameters
        assert "name" in params["properties"]
        assert "task" in params["properties"]
        assert params["required"] == ["name", "task"]

    def test_definition_permission(self):
        assert AGENT_TOOL_DEFINITION.permission == "r"

    def test_definition_tags(self):
        assert "agents" in AGENT_TOOL_DEFINITION.tags


class TestCallAgentHandler:
    def test_handler_calls_dispatch(self):
        """Handler calls registry.dispatch() synchronously."""
        mock_registry = MagicMock()
        mock_registry.dispatch.return_value = (
            "Agent 'reviewer' dispatched with task: Review auth.py\n"
            "The agent is running in the background. "
            "You will receive its summary when it completes."
        )

        handler = create_call_agent_handler(mock_registry)
        result = handler(name="reviewer", task="Review auth.py")

        mock_registry.dispatch.assert_called_once_with("reviewer", "Review auth.py")
        assert "dispatched" in result.lower()

    def test_handler_returns_error_for_unknown_agent(self):
        mock_registry = MagicMock()
        mock_registry.dispatch.return_value = "Error: Agent 'unknown' not found"

        handler = create_call_agent_handler(mock_registry)
        result = handler(name="unknown", task="do something")

        assert "not found" in result.lower() or "error" in result.lower()

    def test_handler_returns_dispatch_result_directly(self):
        """Handler returns whatever registry.dispatch() returns."""
        mock_registry = MagicMock()
        mock_registry.dispatch.return_value = "Agent 'writer' dispatched with task: Write tests..."

        handler = create_call_agent_handler(mock_registry)
        result = handler(name="writer", task="Write tests for auth.py")

        assert result == "Agent 'writer' dispatched with task: Write tests..."

    def test_handler_converts_int_run_id_to_success_string(self):
        """When dispatch succeeds (returns int run_id), handler returns a success string."""
        mock_registry = MagicMock()
        mock_registry.dispatch.return_value = 1  # int run_id

        handler = create_call_agent_handler(mock_registry)
        result = handler(name="reviewer", task="Review auth.py")

        assert isinstance(result, str)
        assert "dispatched" in result.lower()
        assert "reviewer" in result
