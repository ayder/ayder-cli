"""Built-in MCP discovery, default exposure, and permission regression tests."""

import json
from unittest.mock import MagicMock

import pytest
from mcp.types import Tool

from ayder_cli.application.execution_policy import ExecutionPolicy
from ayder_cli.application.validation import SchemaValidator, ToolRequest
from ayder_cli.core.context import ProjectContext
from ayder_cli.core.result import ToolSuccess
from ayder_cli.tools import definition, mcp, plugin_status, schemas
from ayder_cli.tools.registry import create_default_registry


@pytest.fixture(autouse=True)
def isolate_mcp(monkeypatch):
    monkeypatch.setattr(mcp, "_clients", {})
    monkeypatch.setattr(plugin_status, "_status", {})
    monkeypatch.setattr(
        definition,
        "TOOL_DEFINITIONS_BY_NAME",
        dict(definition.TOOL_DEFINITIONS_BY_NAME),
    )
    monkeypatch.setattr(schemas, "TOOL_PERMISSIONS", dict(schemas.TOOL_PERMISSIONS))
    # ExecutionPolicy holds a reference to the map.
    monkeypatch.setattr(
        "ayder_cli.application.execution_policy.TOOL_PERMISSIONS",
        schemas.TOOL_PERMISSIONS,
    )
    yield
    mcp.close_mcp_clients()


def configure(root, servers):
    (root / ".ayder").mkdir(exist_ok=True)
    (root / ".ayder/mcp.json").write_text(json.dumps({"mcpServers": servers}))


def tool(name):
    return Tool(
        name=name,
        description="Remote tool",
        inputSchema={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    )


def fake_client(monkeypatch, results):
    client = MagicMock()
    client.connect_server.side_effect = results
    client.sessions = {"remote": object()}
    client.make_handler.side_effect = lambda server, name: (
        lambda **kwargs: ToolSuccess(kwargs["query"])
    )
    factory = MagicMock(return_value=client)
    monkeypatch.setattr(mcp, "MCPClient", factory)
    return client, factory


def test_default_registry_exposes_mcp_and_dispatches(tmp_path, monkeypatch):
    configure(tmp_path, {"remote": {"url": "http://localhost/mcp"}})
    client, factory = fake_client(monkeypatch, [[tool("remote_search")]])
    # Config is selected by project context, even when cwd differs.
    monkeypatch.chdir(tmp_path.parent)
    registry = create_default_registry(ProjectContext(str(tmp_path)))
    names = {
        s["function"]["name"]
        for s in registry.get_schemas(frozenset({"core", "metadata"}))
    }
    assert "remote_search" in names
    assert registry.execute("remote_search", {"query": "hello"}) == "hello"
    td = definition.TOOL_DEFINITIONS_BY_NAME["remote_search"]
    assert td.parameters["required"] == ["query"]
    valid, error = SchemaValidator().validate(ToolRequest("remote_search", {}))
    assert not valid
    assert error.field == "query"
    assert (
        ExecutionPolicy({"r"}).check_permission("remote_search").required_permission
        == "http"
    )
    assert ExecutionPolicy({"http"}).check_permission("remote_search") is None
    assert "core" in plugin_status.get_all()
    # Delegated agents construct another registry but reuse the connection.
    second = create_default_registry(ProjectContext(str(tmp_path)))
    assert "remote_search" in second.get_registered_tools()
    factory.assert_called_once_with(tmp_path)
    client.connect_server.assert_called_once()


def test_stdio_requires_execute_permission(tmp_path, monkeypatch):
    configure(tmp_path, {"local": {"command": "python", "args": ["server.py"]}})
    fake_client(monkeypatch, [[tool("local_search")]])
    create_default_registry(ProjectContext(str(tmp_path)))
    assert (
        ExecutionPolicy({"r", "http"})
        .check_permission("local_search")
        .required_permission
        == "x"
    )


def test_collisions_preserve_existing_tools(tmp_path, monkeypatch):
    configure(tmp_path, {"remote": {"url": "http://localhost/mcp"}})
    fake_client(monkeypatch, [[tool("read_file"), tool("read_file"), tool("agent")]])
    registry = create_default_registry(ProjectContext(str(tmp_path)))
    assert {
        "read_file",
        "remote__read_file",
        "remote__read_file_2",
        "remote__agent",
    } <= set(registry.get_registered_tools())
    assert definition.TOOL_DEFINITIONS_BY_NAME["read_file"].permission == "r"


@pytest.mark.parametrize("content", ["not json", "[]", '{"mcpServers": []}', "{}"])
def test_invalid_or_empty_config_does_not_start_client(tmp_path, monkeypatch, content):
    (tmp_path / ".ayder").mkdir()
    (tmp_path / ".ayder/mcp.json").write_text(content)
    factory = MagicMock()
    monkeypatch.setattr(mcp, "MCPClient", factory)
    assert (
        "read_file"
        in create_default_registry(ProjectContext(str(tmp_path))).get_registered_tools()
    )
    factory.assert_not_called()


def test_missing_config_does_not_start_client(tmp_path, monkeypatch):
    factory = MagicMock()
    monkeypatch.setattr(mcp, "MCPClient", factory)
    create_default_registry(ProjectContext(str(tmp_path)))
    factory.assert_not_called()


def test_failed_server_does_not_hide_healthy_tools(tmp_path, monkeypatch):
    configure(tmp_path, {"bad": {"url": "bad"}, "good": {"url": "good"}})
    fake_client(monkeypatch, [RuntimeError("offline"), [tool("healthy")]])
    registry = create_default_registry(ProjectContext(str(tmp_path)))
    assert "healthy" in registry.get_registered_tools()


def test_projects_get_separate_clients(tmp_path, monkeypatch):
    second = tmp_path / "second"
    second.mkdir()
    for root in (tmp_path, second):
        configure(root, {"remote": {"url": "http://localhost/mcp"}})
    _, factory = fake_client(monkeypatch, [[tool("a")], [tool("b")]])
    first_reg = create_default_registry(ProjectContext(str(tmp_path)))
    second_reg = create_default_registry(ProjectContext(str(second)))
    assert factory.call_count == 2
    assert "a" not in second_reg.get_registered_tools()
    assert "b" not in first_reg.get_registered_tools()


def test_legacy_plugin_is_skipped_before_import(tmp_path):
    from ayder_cli.tools.plugin_manager import load_plugin_definitions

    (tmp_path / "plugin.toml").write_text("""
[plugin]
name = "mcp-tool"
version = "1.0.0"
api_version = 1
description = "Legacy MCP"
author = "ayder"
[tools]
definitions = "should_not_import.py"
""")
    assert load_plugin_definitions(tmp_path) == ((), {})


def test_parent_and_agent_runtime_freeze_mcp_schemas(tmp_path, monkeypatch):
    from ayder_cli.agents.config import AgentConfig
    from ayder_cli.application import runtime_factory
    from ayder_cli.core.config import Config

    configure(tmp_path, {"remote": {"url": "http://localhost/mcp"}})
    client, _ = fake_client(monkeypatch, [[tool("remote_search")]])
    monkeypatch.setattr(runtime_factory.provider_orchestrator, "create", MagicMock())
    managers = [MagicMock(), MagicMock()]
    monkeypatch.setattr(
        runtime_factory.context_manager_factory,
        "create",
        MagicMock(side_effect=managers),
    )
    parent = runtime_factory.create_runtime(config=Config(), project_root=str(tmp_path))
    agent = runtime_factory.create_agent_runtime(
        agent_config=AgentConfig(name="reviewer", system_prompt="Review"),
        parent_config=parent.config,
        project_ctx=parent.project_ctx,
        process_manager=parent.process_manager,
        permissions={"r"},
    )
    assert parent.tool_registry is not agent.tool_registry
    for manager in managers:
        frozen_schemas = manager.freeze_system_prompt.call_args.args[1]
        assert "remote_search" in {s["function"]["name"] for s in frozen_schemas}
    client.connect_server.assert_called_once()
