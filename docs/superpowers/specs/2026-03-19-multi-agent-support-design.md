# Multi-Agent Support Design

## Goal

Add multi-agent support to ayder-cli so users can define specialized agents (each with its own LLM provider, model, and system prompt) that run as independent agentic loops with isolated context windows, producing structured summaries injected back into the main agent's context.

## Architecture

Agents are first-class runtime objects. Each agent runs an isolated `ChatLoop` (the existing TUI chat loop, renamed and relocated to be reusable) with its own `RuntimeComponents` from `create_runtime()`. An `AgentRegistry` manages agent lifecycle. Agents are dispatched by the user (`/agent` command) or by the main LLM (via a `call_agent` tool). A dedicated `AgentPanel` widget in the TUI shows active agent progress.

## Tech Stack

Python 3.12, Textual (TUI), asyncio, Pydantic (config), existing ayder-cli `create_runtime()` composition root.

## Phased Delivery

- **Phase 1:** Extract reusable `ChatLoop` from `TuiChatLoop` (rename + relocate to `loops/`)
- **Phase 2:** Implement full agent system (config, registry, runner, panel, tool, `/agent` command)

---

## Phase 1: Extract Reusable ChatLoop

### Problem

`TuiChatLoop` in `tui/chat_loop.py` contains the full LLM call + tool routing + tool execution loop. It is widget-free and communicates through a `TuiCallbacks` protocol. Despite being generic, it lives in `tui/` and has TUI-prefixed names, preventing reuse by agents (or CLI).

### Solution

Rename and relocate to `loops/chat_loop.py`:
- `TuiChatLoop` → `ChatLoop`
- `TuiCallbacks` → `ChatCallbacks`
- `TuiLoopConfig` → `ChatLoopConfig`

No naming collision exists — there is no other `ChatLoop` class in the codebase (verified via grep). The CLI uses `cli_runner.py` with inline logic, not a `ChatLoop` class.

`tui/chat_loop.py` becomes a thin backward-compatibility re-export:
```python
from ayder_cli.loops.chat_loop import ChatLoop as TuiChatLoop
from ayder_cli.loops.chat_loop import ChatCallbacks as TuiCallbacks
from ayder_cli.loops.chat_loop import ChatLoopConfig as TuiLoopConfig
```

### Files Affected

| Action | File | Purpose |
|--------|------|---------|
| **Move** | `tui/chat_loop.py` → `loops/chat_loop.py` | Core chat loop logic |
| **Create** | `tui/chat_loop.py` (new) | Backward-compat re-exports |
| **Modify** | `tui/app.py` | Import from new location (or keep using re-exports) |
| **Modify** | `loops/__init__.py` | Export ChatLoop, ChatCallbacks, ChatLoopConfig |
| **Modify** | Tests referencing TuiChatLoop | Update imports |
| **Modify** | `AGENTS.md`, `docs/PROJECT_STRUCTURE.md` | Update structure docs |

### Constraints

- Zero behavior change. Re-exports in `tui/chat_loop.py` ensure all existing imports and tests continue to work without modification. Tests may optionally be updated to use new names, but this is not required.
- `ChatLoop` must remain widget-free and only depend on `loops/base.py`, `providers/base.py`, `tools/registry.py`, `core/context_manager.py`, and `application/execution_policy.py`.

---

## Phase 2: Full Agent System

### Agent Configuration

Agents are defined in `~/.ayder/config.toml`:

```toml
[app]
agent_timeout = 300    # global timeout for all agents (seconds, default 300)

[agents.code-reviewer]
name = "code-reviewer"
provider = "anthropic"          # optional, inherits from [app].provider
model = "claude-sonnet-4-5"     # optional, inherits from active provider model
system_prompt = "You are a strict code reviewer..."

[agents.test-writer]
name = "test-writer"
system_prompt = "You write comprehensive pytest tests."
# provider, model inherited from main config
```

**`AgentConfig`** (Pydantic `BaseModel` in `agents/config.py`, consistent with all other config models):
```python
class AgentConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    provider: str | None = None      # None = inherit from main
    model: str | None = None         # None = inherit from main
    system_prompt: str = ""
```

The `name` field is derived from the TOML key (e.g., `[agents.code-reviewer]` → `name="code-reviewer"`). If both the key and an explicit `name` field are present, the TOML key wins.

**`AgentSummary`** uses `@dataclass` (not Pydantic) because it is purely runtime state, never deserialized from TOML.

**`Config` additions** (in `core/config.py`):
- New field: `agent_timeout: int = 300` (in `[app]` section)
- New field: `agents: dict[str, AgentConfig] = {}` (parsed from `[agents.*]` TOML sections)
- The `flatten_nested_sections` model validator must be updated to parse `[agents.*]` sub-tables, constructing `AgentConfig` objects with `name` derived from the dict key.

**Provider resolution for agents:** When `AgentConfig.provider` is set (e.g., `"anthropic"`), the agent's runtime uses `load_config_for_provider(provider)` to resolve the full LLM profile (`driver`, `api_key`, `base_url`, `model`) from the corresponding `[llm.anthropic]` section. If `AgentConfig.model` is also set, it overrides the profile's model. If `AgentConfig.provider` is `None`, the main config's active provider is inherited.

### Agent Runtime Components

#### File Layout
```
src/ayder_cli/agents/
  ├── __init__.py
  ├── config.py          # AgentConfig dataclass
  ├── registry.py        # AgentRegistry (lifecycle management)
  ├── runner.py           # AgentRunner (isolated loop execution)
  ├── summary.py          # AgentSummary dataclass
  └── tool.py             # call_agent tool definition + handler
```

#### AgentSummary (`agents/summary.py`)
```python
@dataclass
class AgentSummary:
    agent_name: str
    status: str          # "completed" | "timeout" | "error"
    summary: str         # what the agent accomplished (even partial)
    error: str | None    # error details if status != "completed"
```

#### AgentRunner (`agents/runner.py`)

Wraps a `ChatLoop` execution for one agent run. Disposable (one instance per dispatch).

- Creates an agent-specific runtime via `create_agent_runtime()` — a new factory function in `application/runtime_factory.py` that does NOT call `create_runtime()` internally. Instead it assembles components directly:
  1. Resolves the agent's provider profile via `load_config_for_provider()` if `AgentConfig.provider` is set, otherwise uses the parent's `Config`
  2. Applies `AgentConfig.model` override via `cfg.model_copy(update={"model": ...})` if set
  3. Creates a new `AIProvider` via `provider_orchestrator.create(resolved_config)` (isolated per agent)
  4. Creates a new `ToolRegistry` via `create_default_registry(project_ctx, process_manager=pm)` using the **parent's** shared `ProcessManager` and `ProjectContext`
  5. Builds agent system prompt from `AgentConfig.system_prompt` + summary suffix + tool prompts
  6. The agent's `ContextManager` gets its `num_ctx` from the resolved config (chain: `AgentConfig.provider` → `load_config_for_provider()` → `Config.num_ctx`)
  7. The agent's `ChatLoopConfig.permissions` is set to the parent's global permission set (passed in as a parameter)
- Seeds messages: `[system_prompt + summary_suffix, user_task]`
- Runs `ChatLoop` with `AgentCallbacks` (routes events to `AgentPanel`)
- On completion: parses `<agent-summary>` block from final response
- On timeout: constructs `AgentSummary` programmatically with partial progress
- On error: constructs `AgentSummary` with error details

**Shared vs isolated resources:**
| Resource | Shared? | Rationale |
|----------|---------|-----------|
| `ProcessManager` | Shared | Global process limit must be enforced across all agents |
| `ProjectContext` | Shared | All agents work on the same project |
| `AIProvider` | Isolated | Each agent may use a different LLM |
| `ToolRegistry` | Isolated | Each agent needs its own tool schemas and execution context |
| `ContextManager` | Isolated | Each agent has its own token budget (determined by its model's context window via `num_ctx`) |
| `messages` list | Isolated | Independent context window per agent |

**Tool confirmation behavior:** Agents auto-approve all tool confirmations. `AgentCallbacks.request_confirmation()` returns approval immediately without user interaction. This is intentional — agents operate autonomously within the global `ExecutionPolicy` permissions boundary.

**Cancellation wiring:** `AgentRunner` holds an `asyncio.Event` (`_cancelled`). `AgentCallbacks.is_cancelled()` checks this event. `/agent cancel <name>` and `AgentRegistry.cancel()` set the event, causing the `ChatLoop` to exit at the next iteration checkpoint.

**Summary generation:** The agent's system prompt is appended with a standard suffix instructing it to end with a structured `<agent-summary>` block. No extra LLM call needed. If parsing fails, the full last message is used as the summary.

#### AgentRegistry (`agents/registry.py`)

Singleton per app session. Manages lifecycle of all agents.

```
AgentRegistry
  ├── agents: dict[str, AgentConfig]     # loaded from config
  ├── active: dict[str, AgentRunner]     # currently running
  ├── _summary_queue: asyncio.Queue[AgentSummary]  # async-safe result queue
  │
  ├── dispatch(name, task, *, blocking=False, callbacks=None) → AgentSummary  # blocking
  ├── dispatch_async(name, task, *, callbacks=None) → AgentRunner             # non-blocking
  ├── cancel(name) → bool
  ├── get_status(name) → "idle" | "running" | "completed" | "error"
  └── get_capability_prompts() → str     # injected into main LLM system prompt
```

**Dispatch methods (separate for clean types):**
- `dispatch(name, task)` (LLM-dispatched via tool call): `async`, awaits full agent run. Returns `AgentSummary`. Main loop pauses but agent panel shows progress.
- `dispatch_async(name, task)` (user-dispatched via `/agent`): Creates `asyncio.Task`, returns `AgentRunner` immediately. Summary pushed to `_summary_queue` when done, injected as system message at next main loop checkpoint.

#### call_agent Tool (`agents/tool.py`)

A builtin tool registered at startup. Schema:
```json
{
  "name": "call_agent",
  "description": "Delegate a task to a specialized agent",
  "parameters": {
    "name": {"type": "string", "description": "Agent name from config"},
    "task": {"type": "string", "description": "Task description for the agent"}
  }
}
```

Handler calls `await agent_registry.dispatch(name, task)` and returns the `AgentSummary` formatted as a string.

#### Capability Prompt Injection

`AgentRegistry.get_capability_prompts()` generates text appended to the main LLM's system prompt. Agent descriptions are truncated to the first 100 characters to prevent prompt bloat:

```
## Available Agents
You can delegate tasks to specialized agents using the call_agent tool.
Each agent runs independently with its own context and may use a different LLM.

- code-reviewer: You are a strict code reviewer. Analyze code for bugs...
- test-writer: You write comprehensive pytest tests for Python code.
```

Called during `create_runtime()` and appended to the system prompt. If no agents are configured, `get_capability_prompts()` returns an empty string and the `call_agent` tool is not registered.

### TUI Integration

#### AgentPanel Widget

New widget in `tui/widgets.py` (or separate file), similar to existing `ToolPanel`:
- Shows active agents with name, status, elapsed time
- Live progress: streaming output from `AgentCallbacks`
- Completed agents show summary
- Placed below `ToolPanel` in the `AyderApp.compose()` layout, above `StatusBar`. Collapsible when no agents are active.

#### AgentCallbacks

Implements the full `ChatCallbacks` protocol (all methods required). Routes to `AgentPanel`:
- `on_assistant_content()` → agent panel progress display
- `on_tool_start()` / `on_tool_complete()` → agent panel tool activity
- `on_thinking_start()` / `on_thinking_stop()` → agent panel thinking indicator
- `on_thinking_content()` → agent panel thinking text (collapsed by default)
- `on_token_usage()` → agent panel token counter
- `on_tools_cleanup()` → no-op (agent panel manages its own cleanup)
- `on_system_message()` → agent panel system message display
- `request_confirmation()` → auto-approve (returns immediately, agents run autonomously)
- `is_cancelled()` → checks `AgentRunner._cancelled` asyncio.Event

#### /agent Command

Added to `tui/commands.py`:
```
/agent <name> <task>     — dispatch agent with task
/agent list              — show configured agents and their status
/agent cancel <name>     — cancel running agent
```

### Permissions

Agents inherit global permissions from the `ExecutionPolicy` set at startup or via `/permissions`. No per-agent permissions in this phase. Config schema leaves room for a future optional `permissions` field on `AgentConfig`.

### Context Injection

- **LLM-dispatched (blocking):** `AgentSummary` returned as tool result. Main LLM reads status and reacts naturally.
- **User-dispatched (non-blocking):** `AgentRegistry` queues completed summaries in an `asyncio.Queue`. The main `ChatLoop` checks this queue at the **top of each iteration** (before the LLM call), injecting pending summaries as system messages:
  ```
  [Agent "code-reviewer" completed]
  STATUS: completed
  FINDINGS: Found 3 security issues in auth module...
  FILES_CHANGED: none
  RECOMMENDATIONS: Fix SQL injection in login handler
  ```
- **Timeout/error:** Summary always produced with appropriate status. Main LLM can decide whether to retry, adjust scope, or inform user.

### Error Handling

| Scenario | Behavior |
|----------|----------|
| Agent name not found | Tool returns error / command shows error message |
| Agent already running (same name) | Reject dispatch, inform caller. Concurrent runs of the same agent type are intentionally restricted; use different agent names for parallel tasks. |
| Agent timeout | Produce AgentSummary with status="timeout", partial progress |
| Agent LLM error | Produce AgentSummary with status="error", error details |
| Agent tool execution error | Handled by ChatLoop's existing error handling |
| User cancels agent | AgentRunner.cancel() stops the loop, produces summary |

---

## What Needs Refactoring

1. **`TuiChatLoop` rename/relocate** (Phase 1) — prerequisite for agent reuse
2. **`Config` model** — add `agent_timeout` field and `agents` dict; update `flatten_nested_sections` to parse `[agents.*]` sections
3. **`create_runtime()`** — add new `create_agent_runtime()` factory function in `application/runtime_factory.py` that accepts `AgentConfig` + shared `ProcessManager`/`ProjectContext`/permissions, resolves provider profile, assembles agent-specific components directly (does NOT call `create_runtime()`). Main `create_runtime()` integrates `AgentRegistry.get_capability_prompts()` into system prompt.
4. **`ChatLoop.run()`** — add a pre-iteration hook or injection point at the top of each iteration for the main loop to check the `AgentRegistry._summary_queue` and inject pending agent summaries as system messages before the LLM call
5. **`tui/app.py`** — initialize `AgentRegistry`, mount `AgentPanel`, wire summary injection via the pre-iteration hook
6. **`tui/commands.py`** — add `/agent` command handler

## Out of Scope

- Per-agent permissions (future enhancement)
- Per-agent timeout overrides (future enhancement)
- Agent-to-agent communication (agents only communicate via the main agent's context)
- CLI interface for agents (TUI only for now)
- Agent persistence across sessions
