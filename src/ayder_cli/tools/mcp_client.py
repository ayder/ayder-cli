"""MCP sessions and the synchronous tool-dispatch bridge.

Adapted from ayder-plugins/mcp-tool. Each project owns a client, shared by its
main and delegated agents. Sessions stay on one background event loop, with
transport entry and exit in the same task (required by the SDK's task groups).
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import os
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client
from mcp.types import TextContent, Tool

from ayder_cli.core.result import ToolError, ToolSuccess
from ayder_cli.log import get_logger

logger = get_logger("tool")
TIMEOUT = 30


class MCPClient:
    """Keep project MCP sessions alive and expose synchronous handlers."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.sessions: dict[str, ClientSession] = {}
        self._tasks: set[asyncio.Task] = set()
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._loop.run_forever, name="ayder-mcp", daemon=True
        )
        self._thread.start()

    def _build_transport(self, config: dict[str, Any]) -> Any:
        if "url" in config:
            return streamablehttp_client(config["url"])
        params = StdioServerParameters(
            command=config["command"],
            args=config.get("args", []),
            env={**os.environ, **config.get("env", {})},
            cwd=str(self.project_root),
        )
        return stdio_client(params)

    async def _run_server(
        self,
        name: str,
        config: dict[str, Any],
        ready: concurrent.futures.Future[list[Tool]],
    ) -> None:
        task = asyncio.current_task()
        assert task is not None
        self._tasks.add(task)
        try:
            # stdio yields two streams; Streamable HTTP also yields a session-id
            # callback. Both use the first two entries for ClientSession.
            async with self._build_transport(config) as transport:
                async with ClientSession(transport[0], transport[1]) as session:
                    await session.initialize()
                    tools: list[Tool] = []
                    cursor = None
                    while True:
                        result = await session.list_tools(cursor=cursor)
                        tools.extend(result.tools)
                        cursor = result.nextCursor
                        if not cursor:
                            break
                    self.sessions[name] = session
                    ready.set_result(tools)
                    await asyncio.Event().wait()
        except Exception as exc:  # noqa: BLE001 - MCP transport boundary: isolate a failed server from the agent runtime
            logger.opt(exception=True).debug("MCP session failed")
            if not ready.done():
                ready.set_exception(exc)
        finally:
            self.sessions.pop(name, None)
            self._tasks.discard(task)

    def connect_server(self, name: str, config: dict[str, Any]) -> list[Tool]:
        """Connect, initialize, and list tools, with a bounded startup wait."""
        ready: concurrent.futures.Future[list[Tool]] = concurrent.futures.Future()
        future = asyncio.run_coroutine_threadsafe(
            self._run_server(name, config, ready), self._loop
        )
        try:
            return ready.result(timeout=TIMEOUT)
        except TimeoutError:
            future.cancel()
            raise

    def make_handler(
        self, server_name: str, tool_name: str
    ) -> Callable[..., ToolSuccess | ToolError]:
        """Return a handler that forwards arguments unchanged to the server."""

        def handler(**kwargs: Any) -> ToolSuccess | ToolError:
            if self._loop.is_closed():
                return ToolError("MCP client is closed")

            async def call() -> ToolSuccess | ToolError:
                session = self.sessions.get(server_name)
                if session is None:
                    return ToolError(f"MCP server '{server_name}' not connected")
                result = await session.call_tool(tool_name, kwargs)
                texts = [c.text for c in result.content if isinstance(c, TextContent)]
                output = "\n".join(texts)
                if not output and result.structuredContent is not None:
                    output = json.dumps(result.structuredContent)
                if result.isError:
                    return ToolError(f"MCP error: {output or '(no output)'}")
                return ToolSuccess(output or "(no output)")

            future = asyncio.run_coroutine_threadsafe(call(), self._loop)
            try:
                return future.result(timeout=TIMEOUT)
            except TimeoutError:
                future.cancel()
                return ToolError(f"MCP tool call timed out after {TIMEOUT}s")
            except Exception:  # noqa: BLE001 - MCP tool boundary: remote failures become tool results
                logger.opt(exception=True).debug("MCP tool call failed")
                return ToolError(
                    "MCP tool call failed; check the MCP server connection"
                )

        return handler

    def close(self) -> None:
        """Close sessions and subprocesses before stopping the loop thread."""
        if self._loop.is_closed():
            return

        async def shutdown() -> None:
            tasks = list(self._tasks)
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

        future = asyncio.run_coroutine_threadsafe(shutdown(), self._loop)
        try:
            future.result(timeout=5)
        except TimeoutError:
            logger.warning("MCP shutdown timed out")
        finally:
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(timeout=5)
            if not self._thread.is_alive():
                self._loop.close()
