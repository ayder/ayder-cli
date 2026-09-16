"""Load built-in MCP tools from the active project's .ayder/mcp.json."""

from __future__ import annotations

import atexit
import json
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mcp.types import Tool

from ayder_cli.log import get_logger
from ayder_cli.tools.definition import ToolDefinition
from ayder_cli.tools.mcp_client import MCPClient
from ayder_cli.tools.plugin_status import set_status

if TYPE_CHECKING:
    from ayder_cli.tools.registry import ToolRegistry

logger = get_logger("tool")
# A project's agents share connections, but each registry gets its own schemas.
_clients: dict[Path, tuple[MCPClient, list[tuple[str, str, Tool]]]] = {}
_lock = threading.Lock()


def _load_config(root: Path) -> dict[str, Any]:
    try:
        data = json.loads((root / ".ayder" / "mcp.json").read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(
            data.get("mcpServers", {}), dict
        ):
            raise ValueError("mcpServers must be an object")
        return data.get("mcpServers", {})
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        logger.warning("Invalid .ayder/mcp.json; MCP tools unavailable")
        set_status("core", "MCP", "red")
        return {}


def _resolve_name(natural: str, server: str, taken: set[str]) -> str:
    if natural not in taken:
        return natural
    base = f"{server}__{natural}"
    candidate = base
    suffix = 2
    while candidate in taken:
        candidate = f"{base}_{suffix}"
        suffix += 1
    return candidate


def register_mcp_tools(registry: ToolRegistry) -> None:
    """Expose configured MCP tools as core tools in every default registry."""
    root = registry.project_ctx.root
    with _lock:
        cached = _clients.get(root)
        if cached is None:
            servers = _load_config(root)
            if not servers:
                return
            client = MCPClient(root)
            discovered: list[tuple[str, str, Tool]] = []
            for name, config in servers.items():
                try:
                    if not isinstance(config, dict):
                        raise ValueError("MCP server configuration must be an object")
                    tools = client.connect_server(name, config)
                except Exception:  # noqa: BLE001 - optional server boundary: one failed MCP must not prevent other tools loading
                    logger.opt(exception=True).warning("MCP server failed to connect")
                    continue
                permission = "http" if "url" in config else "x"
                discovered.extend((name, permission, tool) for tool in tools)
            cached = (client, discovered)
            _clients[root] = cached
        client, discovered = cached

    taken = set(registry.get_registered_tools())
    # Reserved for the dynamically installed agent dispatcher.
    taken.add("agent")
    for server, permission, tool in discovered:
        name = _resolve_name(tool.name, server, taken)
        taken.add(name)
        definition = ToolDefinition(
            name=name,
            description=f"[{server}] {tool.description or tool.name}",
            parameters=tool.inputSchema,
            tags=("core",),
            permission=permission,
        )
        registry.register_dynamic_tool(
            definition, client.make_handler(server, tool.name)
        )
    # Badge uses its capability tag so /plugin cannot disable built-in MCP.
    connected = sorted(client.sessions)
    set_status(
        "core",
        "MCP: " + ", ".join(connected) if connected else "MCP",
        "green" if connected else "red",
    )


def close_mcp_clients() -> None:
    """Release shared MCP sessions at process exit."""
    with _lock:
        for client, _ in _clients.values():
            client.close()
        _clients.clear()


atexit.register(close_mcp_clients)
