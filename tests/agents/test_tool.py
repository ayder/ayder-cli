"""Tests for the call_agent tool definition and handler."""

import json
from unittest.mock import MagicMock

from ayder_cli.agents.tool import (
    AGENT_TOOL_DEFINITION,
    LIST_AGENTS_TOOL_DEFINITION,
    create_call_agent_handler,
    create_list_agents_handler,
)
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
        # task_id / branch_name are optional assignment metadata.
        assert "task_id" in params["properties"]
        assert "branch_name" in params["properties"]
        # Only the agent name is required: task may be supplied via task_id instead.
        assert params["required"] == ["name"]

    def test_definition_permission(self):
        assert AGENT_TOOL_DEFINITION.permission == "r"

    def test_definition_tags(self):
        assert "agents" in AGENT_TOOL_DEFINITION.tags


class TestListAgentsToolDefinition:
    def test_definition_is_tool_definition(self):
        assert isinstance(LIST_AGENTS_TOOL_DEFINITION, ToolDefinition)

    def test_definition_name(self):
        assert LIST_AGENTS_TOOL_DEFINITION.name == "list_agents"

    def test_definition_has_no_required_parameters(self):
        params = LIST_AGENTS_TOOL_DEFINITION.parameters
        assert params["properties"] == {}
        assert params["required"] == []

    def test_definition_permission(self):
        assert LIST_AGENTS_TOOL_DEFINITION.permission == "r"


class TestListAgentsHandler:
    def test_handler_returns_structured_agents(self):
        mock_registry = MagicMock()
        mock_registry.list_agents.return_value = [
            {
                "name": "reviewer",
                "description": "Reviews code",
                "status": "idle",
                "running_count": 0,
            }
        ]
        mock_registry._on_loop = lambda fn: fn()  # list_agents now marshals through _on_loop

        handler = create_list_agents_handler(mock_registry)
        result = json.loads(handler())

        mock_registry.list_agents.assert_called_once_with()
        assert result["agents"][0]["name"] == "reviewer"
        assert result["agents"][0]["status"] == "idle"


class TestCallAgentHandler:
    def test_handler_calls_create_run(self):
        """Handler routes registry.create_run() onto the loop via _on_loop."""
        mock_registry = MagicMock()
        mock_registry._on_loop = lambda fn: fn()
        mock_registry.create_run.return_value = 1
        mock_registry.run_label.return_value = None

        handler = create_call_agent_handler(mock_registry)
        result = handler(name="reviewer", task="Review auth.py")

        mock_registry.create_run.assert_called_once_with(
            "reviewer", "Review auth.py", task_id=None, branch_name=None
        )
        assert "run #1" in result
        assert "read_agent_result" in result

    def test_handler_echoes_bound_task_in_confirmation(self):
        """The dispatch confirmation echoes the task the harness bound the run to,
        so the orchestrator has an in-context run->task map."""
        mock_registry = MagicMock()
        mock_registry._on_loop = lambda fn: fn()
        mock_registry.create_run.return_value = 5
        mock_registry.run_label.return_value = "TASK-010"

        handler = create_call_agent_handler(mock_registry)
        result = handler(name="senior_coder", task_id="TASK-010")

        mock_registry.run_label.assert_called_once_with(5)
        assert "run #5" in result
        assert "for TASK-010" in result

    def test_handler_returns_error_for_unknown_agent(self):
        mock_registry = MagicMock()
        mock_registry._on_loop = lambda fn: fn()
        mock_registry.create_run.return_value = "Error: Agent 'unknown' not found"

        handler = create_call_agent_handler(mock_registry)
        result = handler(name="unknown", task="do something")

        assert "not found" in result.lower() or "error" in result.lower()

    def test_handler_returns_create_run_error_directly(self):
        """Handler returns the error string from create_run unchanged."""
        mock_registry = MagicMock()
        mock_registry._on_loop = lambda fn: fn()
        mock_registry.create_run.return_value = "Error: Agent 'writer' failed in this cycle."

        handler = create_call_agent_handler(mock_registry)
        result = handler(name="writer", task="Write tests for auth.py")

        assert result == "Error: Agent 'writer' failed in this cycle."

    def test_handler_converts_int_run_id_to_success_string(self):
        """When create_run succeeds (returns int run_id), handler returns a success string."""
        mock_registry = MagicMock()
        mock_registry._on_loop = lambda fn: fn()
        mock_registry.create_run.return_value = 1  # int run_id
        mock_registry.run_label.return_value = None

        handler = create_call_agent_handler(mock_registry)
        result = handler(name="reviewer", task="Review auth.py")

        assert isinstance(result, str)
        assert "dispatched" in result.lower()
        assert "reviewer" in result
        assert "run #1" in result
