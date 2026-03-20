# Multi-Instance Agent Support — Design Spec

**Date:** 2026-03-20
**Status:** Approved

## Problem

The agent registry enforces a one-instance-per-name constraint: `if name in self._active: return error`. This prevents running two `code_reviewer` agents concurrently on different tasks. The constraint is artificial — the underlying runner infrastructure supports concurrency, and AgentPanel already uses run-ID-keyed entries.

## Design

### Overview

Remove the one-instance-per-name constraint. Key `_active` by run_id instead of agent name. Return run_id from `dispatch()`. Cancel-by-name cancels all instances. `_settled` guard stays per-name.

### Registry Changes (`src/ayder_cli/agents/registry.py`)

**Data model:**
```python
_run_counter: int = 0
_active: dict[int, AgentRunner]    # run_id -> runner (was dict[str, AgentRunner])
_settled: dict[str, str]           # agent_name -> status (unchanged, per-name)
```

**`dispatch(name, task)` returns `int | str`:**
- On success: returns `run_id` (int). Increments `_run_counter`, creates runner, stores in `_active[run_id]`.
- On error: returns error message (str).
- The `if name in self._active` guard is **removed entirely**.
- The `_settled` guard stays per-name: if agent failed this turn, block re-dispatch regardless of run_id.

**`cancel(name)` cancels all instances:**
```python
def cancel(self, name: str) -> bool:
    """Cancel all running instances of the named agent. Returns True if any were cancelled."""
    to_cancel = [rid for rid, r in self._active.items() if r.agent_name == name]
    for rid in to_cancel:
        self._active[rid].cancel()
    return len(to_cancel) > 0
```

**`active_count` unchanged:** `len(self._active)`.

**`get_status(name)` — behavior change:**

The current `get_status()` only checks `_active` for a running runner. The new version also consults `_settled` and returns an aggregate view:
- "running" if any instance of `name` is in `_active`
- Settled status (from `_settled[name]`) if not running but settled this turn
- "idle" if configured but not running or settled
- `None` if not a configured agent

This is a behavior change from the current implementation, not just an aggregation adjustment. It affects what `/agent list` displays.

**`get_running_count(name)` — new method:**

Returns the number of currently active instances of the named agent:
```python
def get_running_count(self, name: str) -> int:
    return sum(1 for r in self._active.values() if r.agent_name == name)
```

Used by `/agent list` to show instance count.

**Completion callback (`_run_and_queue`):**
- Runner stores `self.run_id` (assigned by registry at dispatch time)
- `_run_and_queue` closures capture `run_id` at creation time
- `self._active.pop(run_id)` instead of `self._active.pop(name)`
- `self._settled[name] = result.status` — per-name, last-writer-wins
- `on_complete` closure passes `run_id` to app callback: `self._on_complete(run_id, result)`
- Batch wake-up still fires when `active_count == 0`

**`_settled` semantics with multiple instances:** If two instances of "reviewer" complete with different statuses (one "completed", one "error"), `_settled["reviewer"]` reflects the **last to complete** (last-writer-wins). This means a subsequent dispatch attempt might be blocked if the last instance failed, even if an earlier one succeeded. This is acceptable — `_settled` is a coarse per-turn guard, not a precise status tracker.

**Runner `run_id` assignment:**
- `AgentRunner.__init__` gains a `run_id: int` parameter
- Runner stores it as `self.run_id`
- Runner passes `run_id` to `AgentCallbacks.__init__`

### Callback Changes (`src/ayder_cli/agents/callbacks.py`)

**`AgentCallbacks` gains `run_id`:**
```python
def __init__(
    self,
    agent_name: str,
    run_id: int,
    cancel_event: asyncio.Event,
    on_progress: Callable[[int, str, str, Any], None] | None = None,
) -> None:
```

**`_emit` passes `run_id`:**
```python
def _emit(self, event: str, data: Any = None) -> None:
    if self._on_progress:
        self._on_progress(self.run_id, self.agent_name, event, data)
```

The `on_progress` callback signature changes from `Callable[[str, str, Any], None]` (name, event, data) to `Callable[[int, str, str, Any], None]` (run_id, name, event, data).

### Runner Changes (`src/ayder_cli/agents/runner.py`)

**`AgentRunner.__init__` gains `run_id: int` parameter:**
```python
def __init__(
    self,
    agent_config: AgentConfig,
    parent_config: Any,
    project_ctx: Any,
    process_manager: Any,
    permissions: set[str],
    timeout: int = 300,
    run_id: int = 0,
    on_progress: Callable[[int, str, str, Any], None] | None = None,
) -> None:
```

Runner passes `run_id` to `AgentCallbacks`:
```python
self._callbacks = AgentCallbacks(
    agent_name=agent_config.name,
    run_id=run_id,
    cancel_event=self._cancel_event,
    on_progress=on_progress,
)
```

### AgentPanel Changes (`src/ayder_cli/tui/widgets.py`)

**Drop `_active_run` dict.** Run_id now comes from the registry via callbacks, not from an internal mapping.

**Drop `_run_counter`.** The registry is the single source of truth for run IDs.

**Method signature changes:**
```python
def add_agent(self, name: str, run_id: int) -> None:
    """Add a new agent run entry. Never auto-shows the panel."""

def complete_agent(self, run_id: int, summary: str, status: str = "completed") -> None:
    """Mark agent as completed with full summary. Lookup by run_id directly."""

def update_agent(self, run_id: int, name: str, event: str, data: Any = None) -> None:
    """Handle an agent progress event. Lookup by run_id. Name is needed for auto-create."""

def remove_agent(self, run_id: int) -> None:
    """Remove an agent entry from the panel by run_id. Defensive only — no callers today."""
```

**`_entries: dict[int, _AgentEntry]` stays as-is** — already keyed by run_id.

**`update_agent` auto-create:** When `run_id` is not in `_entries`, calls `self.add_agent(name, run_id)` internally before processing the event. The `name` parameter is required for this.

### App Callback Changes (`src/ayder_cli/tui/app.py`)

**`_agent_progress` signature changes to receive `run_id`:**
```python
def _agent_progress(run_id, name, event, data):
    # ...
    agent_panel.update_agent(run_id, name, event, data)
```

**`_agent_complete` signature changes to receive `run_id`:**
```python
def _agent_complete(run_id, summary):
    # ...
    agent_panel.complete_agent(run_id, summary.summary, summary.status)
```

Note: `AgentSummary` has `.summary` (not `.text`). The `summary.agent_name` is still available for display/logging.

### Commands Changes (`src/ayder_cli/tui/commands.py`)

**`/agent cancel <name>`:**
- Calls `registry.cancel(name)` which cancels all instances with that name.
- Message: "Cancelled agent 'name'" or "Agent 'name' is not running".

**`/agent list`:**
- Uses `registry.get_running_count(name)` to show instance count.
- Multiple instances: `code_reviewer: running (2 instances)`
- Single instance: `code_reviewer: running` (unchanged)

**`/agent <name> <task>` dispatch:**
- `dispatch()` now returns `int` on success instead of error-string-or-None.
- The handler must check `isinstance(result, int)` for success, `isinstance(result, str)` for error.
- On success, display: "Agent 'name' dispatched" (do not show run_id to user).

### Tool Handler Changes (`src/ayder_cli/agents/tool.py`)

- `dispatch()` now returns `int` on success.
- The handler currently returns `registry.dispatch(...)` directly as a tool result string.
- Must convert: on success (`int`), return a string like `f"Agent '{name}' dispatched successfully"`. On error (`str`), return the error string as-is.

## Files Affected

| File | Change |
|---|---|
| `src/ayder_cli/agents/registry.py` | `_active` keyed by run_id, add `_run_counter`, `dispatch()` returns int, `cancel()` cancels all by name, `get_status()` aggregates, add `get_running_count()` |
| `src/ayder_cli/agents/runner.py` | `AgentRunner` gains `run_id` param, passes it to `AgentCallbacks` |
| `src/ayder_cli/agents/callbacks.py` | `AgentCallbacks` gains `run_id`, `_emit` passes run_id, `on_progress` signature changes |
| `src/ayder_cli/tui/widgets.py` | `AgentPanel` drops `_active_run` and `_run_counter`, methods take `run_id` param |
| `src/ayder_cli/tui/app.py` | Callbacks receive and pass `run_id` to AgentPanel |
| `src/ayder_cli/tui/commands.py` | `/agent cancel` cancels all by name, `/agent list` shows instance count, dispatch handles int return |
| `src/ayder_cli/agents/tool.py` | Handle int return from dispatch, convert to success string |
| `tests/agents/test_registry.py` | Rewrite dispatch guard tests, add multi-instance tests |
| `tests/agents/test_callbacks.py` | Update callback signature tests for run_id |
| `tests/tui/test_widgets.py` | Update AgentPanel tests to pass run_id |

## What Does NOT Change

- `_settled` dict — stays `dict[str, str]` keyed by name
- `reset_settled()` — unchanged
- `AgentConfig` — unchanged
- `AgentSummary` — unchanged (no run_id field; run_id is plumbing, not part of the summary)
- Batch wake-up logic — still fires when `active_count == 0`
- ActivityBar agent count spinner — still uses `active_count`

## Constraints

- `dispatch()` return type: `int` on success, `str` on error
- `_settled` guard stays per-name with last-writer-wins semantics
- `cancel(name)` cancels ALL instances with that name
- No new user-facing concepts — run IDs are internal plumbing
- Existing tests must pass or be intentionally updated
