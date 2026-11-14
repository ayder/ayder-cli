"""MCP session transport, lifecycle, and tool-call tests."""

import asyncio
import os
import sys
import threading
from contextlib import asynccontextmanager
from pathlib import Path
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


# -- a stdio server's stderr goes to its own log file, never the terminal -------


def _fake_stdio(monkeypatch):
    """Stand in for the SDK: record what stdio_client was given, serve one empty session."""
    calls = []

    @asynccontextmanager
    async def transport(params, **kwargs):
        calls.append(kwargs)
        yield ("read", "write")

    session = MagicMock()
    session.initialize = AsyncMock()
    session.list_tools = AsyncMock(return_value=ListToolsResult(tools=[]))
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock()
    monkeypatch.setattr(mcp_client, "stdio_client", transport)
    monkeypatch.setattr(mcp_client, "ClientSession", MagicMock(return_value=session))
    return calls


def test_stdio_server_gets_its_own_errlog_file(client, monkeypatch, tmp_path):
    calls = _fake_stdio(monkeypatch)
    log_dir = tmp_path / "logs"
    monkeypatch.setattr(mcp_client, "get_log_dir", lambda: log_dir)

    client.connect_server("news digest/1", {"command": "x"})

    errlog = calls[0]["errlog"]
    path = log_dir / "mcp-news_digest_1.log"
    assert errlog.name == str(path) and errlog.mode == "a"
    assert not errlog.closed  # held while the server runs
    assert path.read_text().startswith("--- news digest/1 started ")
    client.close()
    assert errlog.closed  # and released when it stops


def test_relative_log_dir_is_taken_from_the_project_root(client, monkeypatch):
    calls = _fake_stdio(monkeypatch)
    monkeypatch.setattr(mcp_client, "get_log_dir", lambda: Path(".ayder/log"))

    client.connect_server("srv", {"command": "x"})

    expected = client.project_root / ".ayder" / "log" / "mcp-srv.log"
    assert calls[0]["errlog"].name == str(expected)
    client.close()


def test_url_server_opens_no_errlog_file(client, monkeypatch, tmp_path):
    session = MagicMock()
    session.initialize = AsyncMock()
    session.list_tools = AsyncMock(return_value=ListToolsResult(tools=[]))
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock()

    @asynccontextmanager
    async def http(url):
        yield ("read", "write", lambda: "id")

    monkeypatch.setattr(mcp_client, "streamablehttp_client", http)
    monkeypatch.setattr(mcp_client, "ClientSession", MagicMock(return_value=session))
    log_dir = tmp_path / "logs"
    monkeypatch.setattr(mcp_client, "get_log_dir", lambda: log_dir)

    client.connect_server("remote", {"url": "http://localhost/mcp"})

    assert not log_dir.exists()
    client.close()


def test_unwritable_log_dir_falls_back_to_devnull(client, monkeypatch, tmp_path):
    calls = _fake_stdio(monkeypatch)
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("")
    monkeypatch.setattr(mcp_client, "get_log_dir", lambda: blocker / "logs")

    tools = client.connect_server("srv", {"command": "x"})  # still starts

    assert tools == []
    assert calls[0]["errlog"].name == os.devnull
    client.close()
