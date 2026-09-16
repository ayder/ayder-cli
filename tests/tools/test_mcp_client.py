"""MCP session transport, lifecycle, and tool-call tests."""

import asyncio
import sys
import threading
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest
from mcp.types import CallToolResult, ListToolsResult, TextContent, Tool

from ayder_cli.core.result import ToolError, ToolSuccess
from ayder_cli.tools import mcp_client


@pytest.fixture
def client(tmp_path):
    instance = mcp_client.MCPClient(tmp_path)
    yield instance
    instance.close()
    assert not instance._thread.is_alive()


def test_stdio_uses_project_root_and_environment(client, monkeypatch):
    transport = MagicMock()
    monkeypatch.setattr(mcp_client, "stdio_client", transport)
    monkeypatch.setenv("MCP_INHERITED", "present")
    client._build_transport(
        {"command": "python", "args": ["server.py"], "env": {"CUSTOM": "value"}}
    )
    params = transport.call_args.args[0]
    assert params.cwd == str(client.project_root)
    assert params.env["MCP_INHERITED"] == "present"
    assert params.env["CUSTOM"] == "value"
    assert params.args == ["server.py"]


@pytest.mark.parametrize("http", [False, True])
def test_session_lifetime_and_paginated_tools(client, monkeypatch, http):
    closed = threading.Event()
    session = MagicMock()
    session.initialize = AsyncMock()
    first = Tool(name="first", inputSchema={"type": "object"})
    second = Tool(name="second", inputSchema={"type": "object"})
    session.list_tools = AsyncMock(
        side_effect=[
            ListToolsResult(tools=[first], nextCursor="page2"),
            ListToolsResult(tools=[second]),
        ]
    )
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock()

    @asynccontextmanager
    async def transport(*args, **kwargs):
        owner = asyncio.current_task()
        try:
            yield ("read", "write", lambda: "session") if http else ("read", "write")
        finally:
            assert asyncio.current_task() is owner
            closed.set()

    monkeypatch.setattr(mcp_client, "streamablehttp_client", transport)
    monkeypatch.setattr(mcp_client, "stdio_client", transport)
    factory = MagicMock(return_value=session)
    monkeypatch.setattr(mcp_client, "ClientSession", factory)
    config = {"url": "http://localhost/mcp"} if http else {"command": "test"}
    assert client.connect_server("server", config) == [first, second]
    factory.assert_called_once_with("read", "write")
    assert not closed.is_set()
    session.list_tools.assert_any_await(cursor="page2")
    client.close()
    assert closed.is_set()
    assert not client.sessions


@pytest.mark.parametrize("is_error", [False, True])
def test_calls_forward_arguments_and_preserve_results(client, is_error):
    session = MagicMock()
    session.call_tool = AsyncMock(
        return_value=CallToolResult(
            content=[
                TextContent(type="text", text="hello"),
                TextContent(type="text", text="world"),
            ],
            isError=is_error,
        )
    )
    client.sessions["server"] = session
    result = client.make_handler("server", "search")(query="value", limit=3)
    assert isinstance(result, ToolError if is_error else ToolSuccess)
    assert "hello\nworld" in result
    session.call_tool.assert_awaited_once_with("search", {"query": "value", "limit": 3})


def test_structured_only_result(client):
    session = MagicMock()
    session.call_tool = AsyncMock(
        return_value=CallToolResult(content=[], structuredContent={"answer": 42})
    )
    client.sessions["server"] = session
    assert client.make_handler("server", "search")() == '{"answer": 42}'


def test_missing_session_is_tool_error(client):
    assert isinstance(client.make_handler("missing", "search")(), ToolError)


def test_tool_timeout_cancels_request(client, monkeypatch):
    cancelled = threading.Event()

    async def call(*args):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    client.sessions["server"] = MagicMock(call_tool=call)
    monkeypatch.setattr(mcp_client, "TIMEOUT", 0.05)
    result = client.make_handler("server", "search")()
    assert isinstance(result, ToolError)
    assert "timed out" in result
    assert cancelled.wait(1)


def test_connect_timeout_closes_transport(client, monkeypatch):
    closed = threading.Event()

    @asynccontextmanager
    async def transport(config):
        try:
            await asyncio.Event().wait()
            yield ()
        finally:
            closed.set()

    monkeypatch.setattr(client, "_build_transport", transport)
    monkeypatch.setattr(mcp_client, "TIMEOUT", 0.05)
    with pytest.raises(TimeoutError):
        client.connect_server("slow", {})
    assert closed.wait(1)


def test_real_stdio_server_round_trip(client):
    server = client.project_root / "server.py"
    server.write_text("""
from mcp.server.fastmcp import FastMCP
server = FastMCP("test")
@server.tool()
def echo(message: str) -> str:
    return "echo: " + message
server.run(transport="stdio")
""")
    tools = client.connect_server(
        "local", {"command": sys.executable, "args": ["server.py"]}
    )
    assert [tool.name for tool in tools] == ["echo"]
    assert client.make_handler("local", "echo")(message="test") == "echo: test"
