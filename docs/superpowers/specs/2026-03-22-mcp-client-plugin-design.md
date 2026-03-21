# MCP Client Plugin Design

**Date:** 2026-03-22
**Status:** Approved

---

## Goal

An ayder plugin (`mcp-tool`) that acts as a dynamic proxy for MCP servers. It reads `.ayder/mcp.json` at plugin load time, connects to each configured server, and registers each remote tool as a first-class ayder tool. The LLM sees MCP tools natively in its tool list — no wrapper abstraction.

---

## File Structure

```
~/Vscode/ayder-plugins/mcp-tool/
├── plugin.toml           # manifest — dep: mcp>=1.0
├── mcp_definitions.py    # definitions file: reads mcp.json, connects, builds TOOL_DEFINITIONS
├── mcp_state.py          # persistent singleton state (never referenced in func_refs)
├── mcp_client.py         # connection management and tool call bridge
└── mcp_tool.py           # func_ref target: module-level __getattr__ dispatcher
```

### plugin.toml

```toml
[plugin]
name        = "mcp-tool"
version     = "1.0.0"
api_version = 1
description = "MCP client proxy — connects to MCP servers and exposes their tools to ayder"
author      = "ayder"

[dependencies]
mcp = ">=1.0"

[tools]
definitions = "mcp_definitions.py"
```

---

## Why Five Files — The Re-import Problem

ayder's `load_plugin_definitions` resolves each tool's `func_ref` by calling `sys.modules.pop(mod_path)` + `importlib.import_module(mod_path)` **once per tool** in a loop. With N MCP tools, `mcp_tool.py` is re-imported N times. Each re-import runs the module from scratch.

`mcp_state.py` is **never referenced in any `func_ref`** and is never popped from `sys.modules` by the loader. It is imported exactly once (by `mcp_definitions.py`) and remains cached. All mutable state — event loop, sessions, handler closures — lives there.

`mcp_tool.py` uses Python's module-level `__getattr__` (PEP 562, Python 3.7+). On each re-import, it runs `from mcp_state import state` (gets the cached singleton), then defines `__getattr__`. When the loader calls `getattr(mcp_tool_module, "filesystem__read_file")`, the attribute is not found normally so `__getattr__("filesystem__read_file")` fires, returning `state.handlers["filesystem__read_file"]` — the closure created by `mcp_client.make_handler()` during the initial connection phase. The loader stores this closure in its `handlers` dict and never touches `mcp_tool.py` again. All subsequent calls go directly to the closure.

---

## Configuration

### `.ayder/mcp.json` — Claude Desktop Compatible Format

Located at project root (cwd when ayder runs). Exact Claude Desktop format:

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
      "env": { "HOME": "/tmp" }
    },
    "fetch": {
      "command": "uvx",
      "args": ["mcp-server-fetch"]
    },
    "my-api": {
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

- `command` + `args` + optional `env` → **stdio transport** (spawns subprocess)
- `url` → **streamable HTTP transport**
- To disable a server: remove its entry (no `disabled` flag)
- File missing → silent, `TOOL_DEFINITIONS = ()`, plugin contributes nothing
- File exists but invalid JSON → DEBUG log only; MCP status bar badge turns **red**

---

## Tool Naming

### Strategy: Natural name first, prefix on conflict

| Situation | Registered as | User notification |
|---|---|---|
| Tool `read_file` from `filesystem`, no existing conflict | `read_file` | none |
| Tool `read_file` from `server_b`, `read_file` already exists | `server_b__read_file` | warning printed to stderr |
| Tool `list_tasks` conflicts with ayder builtin or other plugin | `filesystem__list_tasks` | warning printed to stderr |

**Conflict check order (inside `mcp_definitions.py`):**
1. ayder builtins and globally installed plugins — query via `from ayder_cli.tools.definition import TOOL_DEFINITIONS as _existing; _taken = {td.name for td in _existing}`
2. earlier MCP servers in `mcpServers` key order — track within the current build session
3. Other project-local plugins loaded before this one are not visible at definition time; `_load_project_plugins` in `registry.py` will catch those conflicts and reject the whole plugin with a clear error message (acceptable edge case in v1)

Conflict resolution runs entirely inside `mcp_definitions.py` before `TOOL_DEFINITIONS` is returned. The returned tuple must contain only unique, final names — the loader's atomic pre-check in `_load_project_plugins` will reject the whole plugin if any name still collides.

**Warning format:**
```
[mcp-tool] 'read_file' from server 'server_b' conflicts — registering as 'server_b__read_file'
```

---

## Load Sequence (mcp_definitions.py)

`mcp_definitions.py` runs entirely synchronously at import time. In order:

1. Read and parse `.ayder/mcp.json` from `Path.cwd() / ".ayder" / "mcp.json"`. If missing → `TOOL_DEFINITIONS = (); return`. If invalid JSON → DEBUG log, set red status, `TOOL_DEFINITIONS = (); return`.
2. Call `mcp_client.ensure_loop()` — starts background asyncio thread (idempotent).
3. Build `_taken: set[str]` from existing ayder tool names (builtins + global plugins).
4. For each server in `mcpServers` key order:
   - Call `mcp_client.connect_server(name, config)` — **blocks** via `run_coroutine_threadsafe(...).result(timeout=30)`. Returns list of MCP tools or raises on failure.
   - On failure: DEBUG log, skip server, continue.
   - For each tool: resolve final name (natural or prefixed), warn if prefixed. Call `mcp_client.make_handler(server_name, tool.name)` and store the returned closure in `state.handlers[resolved_name]`. Add `ToolDefinition` to the build list.
5. If no tools discovered: set red status, `TOOL_DEFINITIONS = ()`.
6. Else: set green status.

---

## Connection Management

### Background Event Loop Thread

Started once in `mcp_client.ensure_loop()`, guarded by `mcp_state.state.loop is None`:

```python
state.loop = asyncio.new_event_loop()
state.loop_thread = threading.Thread(target=state.loop.run_forever, daemon=True)
state.loop_thread.start()
```

### Persistent Session Coroutine

Each server gets a long-running task that holds the transport context manager open:

```python
async def _run_server(name, config, tools_ready: asyncio.Future):
    try:
        transport_cm = _build_transport(config)   # stdio_client or streamable_http_client
        async with transport_cm as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.list_tools()
                state.sessions[name] = session
                tools_ready.set_result(result.tools)
                await asyncio.Event().wait()         # keep alive until cancelled
    except Exception as e:
        if not tools_ready.done():
            tools_ready.set_exception(e)
```

`connect_server(name, config)` schedules `_run_server` as a background task and blocks on `tools_ready`. Uses `concurrent.futures.Future` (stdlib, thread-safe) rather than `asyncio.Future` — avoids `asyncio.wrap_future` which is unsafe when called from outside the event loop thread:

```python
def connect_server(name, config):
    import concurrent.futures
    tools_ready = concurrent.futures.Future()
    asyncio.run_coroutine_threadsafe(_run_server(name, config, tools_ready), state.loop)
    return tools_ready.result(timeout=30)   # blocks calling thread until ready or timeout
```

`_run_server` calls `tools_ready.set_result(result.tools)` or `tools_ready.set_exception(e)` (stdlib Future methods are thread-safe and callable from within the event loop).

If a server process dies after load, `state.sessions[name]` becomes unusable. Tool calls return `ToolError` cleanly. No reconnect in v1.

---

## Tool Schema

MCP's `inputSchema` is already JSON Schema — passed directly as `parameters`. Permission is assigned by transport type.

```python
ToolDefinition(
    name=resolved_name,
    description=f"[{server_name}] {tool.description or tool.name}",
    parameters=tool.inputSchema,
    func_ref=f"mcp_tool:{resolved_name}",
    tags=("mcp",),
    permission="x" if "command" in server_config else "http",
    safe_mode_blocked=False,
)
```

---

## Async Bridge (Sync ayder → Async MCP)

`mcp_client.make_handler(server_name, mcp_tool_name)` returns a closure stored in `state.handlers`:

```python
def make_handler(server_name, mcp_tool_name):
    def handler(**kwargs):
        session = state.sessions.get(server_name)
        if session is None:
            return ToolError(f"MCP server '{server_name}' not connected")

        async def _call():
            result = await session.call_tool(mcp_tool_name, kwargs)
            if result.isError:
                error_text = " ".join(
                    c.text for c in result.content if hasattr(c, "text")
                )
                return ToolError(f"MCP error: {error_text}")
            texts = [c.text for c in result.content if hasattr(c, "text")]
            return ToolSuccess("\n".join(texts) if texts else "(no output)")

        future = asyncio.run_coroutine_threadsafe(_call(), state.loop)
        try:
            return future.result(timeout=30)
        except TimeoutError:
            future.cancel()
            return ToolError("MCP tool call timed out after 30s")
        except Exception as e:
            return ToolError(f"MCP tool call failed: {e}")
    return handler
```

---

## Status Bar Integration

Requires a new module added to ayder-cli core as part of this work: `ayder_cli/tools/plugin_status.py`.

```python
# ayder_cli/tools/plugin_status.py
_status: dict[str, tuple[str, str]] = {}   # plugin_name → (label, color)

def set_status(name: str, label: str, color: str) -> None:
    _status[name] = (label, color)

def get_all() -> dict[str, tuple[str, str]]:
    return dict(_status)
```

`mcp_client.py` imports this with a fallback so the plugin works against older ayder-cli versions that don't have the module yet:

```python
try:
    from ayder_cli.tools.plugin_status import set_status as _set_status
except ImportError:
    def _set_status(name, label, color): pass   # no-op fallback
```

The ayder TUI reads `plugin_status.get_all()` to render badges in the status bar. The exact TUI component and render point is a separate concern for the ayder-cli implementation; the plugin only calls `set_status`.

**mcp_client.py** calls:
- `_set_status("mcp", "MCP", "green")` — when ≥1 server connected successfully
- `_set_status("mcp", "MCP", "red")` — when mcp.json invalid or all servers failed

---

## Error Handling Summary

| Situation | Behaviour |
|---|---|
| `mcp.json` missing | Silent — no tools, no badge |
| `mcp.json` invalid JSON | DEBUG log; red MCP badge; no tools |
| Server fails to connect | DEBUG log; server skipped; other servers continue |
| All servers fail | Red MCP badge; `TOOL_DEFINITIONS = ()` |
| Tool name conflict (builtin/plugin) | Prefix applied; warning to stderr at load |
| Session dead at call time | `ToolError("MCP server 'X' not connected")` |
| Tool call timeout (>30s) | `ToolError("MCP tool call timed out after 30s")` |
| MCP error response (`result.isError`) | `ToolError("MCP error: {text}")` |
| Binary/image content in result | Ignored in v1; text content only |

---

## Scope

**In scope (v1):**
- stdio and HTTP transports
- Tool proxy with natural-name-first conflict resolution
- Persistent connections via background event loop thread
- Green/red MCP status bar badge (requires `plugin_status.py` in ayder-cli core)

**Out of scope (v1):**
- Reconnect on server disconnect
- MCP sampling, resource, and prompt capabilities (tools only)
- Binary/image result rendering
- Per-server timeout configuration
- `disabled` flag in mcp.json
