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

**`get_status(name)` returns aggregate:**
- "running" if any instance of `name` is in `_active`
- Settled status if in `_settled` and not running
- "idle" if configured but not running or settled
- `None` if not a configured agent

**Completion callback (`_run_and_queue`):**
- `self._active.pop(run_id)` instead of `self._active.pop(name)`
- `self._settled[name] = result.status` — unchanged (per-name)
- Batch wake-up still fires when `active_count == 0`

**`AgentRunner` receives `run_id`:**
- Registry assigns `run_id` at dispatch time
- Runner stores it as `self.run_id`
- Passes `run_id` to progress and completion callbacks

### AgentPanel Changes (`src/ayder_cli/tui/widgets.py`)

**Drop `_active_run` dict.** Run_id now comes from the registry, not from an internal counter.

**Drop `_run_counter`.** The registry is the single source of truth for run IDs.

**Method signature changes:**
```python
def add_agent(self, name: str, run_id: int) -> None:
    """Add a new agent run entry. Never auto-shows the panel."""

def complete_agent(self, run_id: int, summary: str, status: str = "completed") -> None:
    """Mark agent as completed with full summary. Lookup by run_id directly."""

def update_agent(self, run_id: int, event: str, data: Any = None) -> None:
    """Handle an agent progress event. Lookup by run_id directly."""

def remove_agent(self, run_id: int) -> None:
    """Remove an agent entry from the panel by run_id."""
```

**`_entries: dict[int, _AgentEntry]` stays as-is** — already keyed by run_id.

**`update_agent` auto-create behavior:** When `run_id` is not in `_entries`, the method needs the agent name to create the entry. Change signature to `update_agent(self, run_id: int, name: str, event: str, data: Any = None)`.

### Callback Changes (`src/ayder_cli/tui/app.py`)

**`_agent_progress(run_id, name, event, data)`:**
- Receives `run_id` from the runner
- Calls `agent_panel.update_agent(run_id, name, event, data)`

**`_agent_complete(run_id, summary)`:**
- Receives `run_id` from the runner
- Calls `agent_panel.complete_agent(run_id, summary.text, summary.status)`
- `summary.agent_name` still available for display/logging

### Commands Changes (`src/ayder_cli/tui/commands.py`)

**`/agent cancel <name>`:**
- Calls `registry.cancel(name)` which cancels all instances with that name.
- Message: "Cancelled N instance(s) of agent 'name'" or "Agent 'name' is not running".

**`/agent list`:**
- Shows instance count when multiple are running: `code_reviewer: running (2 instances)`
- Single instance: `code_reviewer: running` (unchanged)

**`/agent <name> <task>` dispatch:**
- Receives `int` back from `dispatch()` on success instead of `None`
- No behavior change needed — run_id is passed to AgentPanel via callbacks

### Tool Handler Changes (`src/ayder_cli/agents/tool.py`)

- `call_agent` handler receives `int` from `registry.dispatch()` on success
- No behavior change — the handler doesn't use the return value beyond checking for error strings

## Files Affected

| File | Change |
|---|---|
| `src/ayder_cli/agents/registry.py` | `_active` keyed by run_id, add `_run_counter`, `dispatch()` returns int, `cancel()` cancels all by name, `get_status()` aggregates |
| `src/ayder_cli/agents/runner.py` | `AgentRunner` stores `run_id`, passes it to callbacks |
| `src/ayder_cli/tui/widgets.py` | `AgentPanel` drops `_active_run` and `_run_counter`, methods take `run_id` param |
| `src/ayder_cli/tui/app.py` | Callbacks pass `run_id` to AgentPanel |
| `src/ayder_cli/tui/commands.py` | `/agent cancel` cancels all by name, `/agent list` shows instance count |
| `src/ayder_cli/agents/tool.py` | Handle int return from dispatch (no behavior change) |
| `tests/agents/test_registry.py` | Rewrite dispatch guard tests, add multi-instance tests |
| `tests/tui/test_widgets.py` | Update AgentPanel tests to pass run_id |

## What Does NOT Change

- `_settled` dict — stays `dict[str, str]` keyed by name
- `reset_settled()` — unchanged
- `AgentConfig`, `AgentSummary` — unchanged
- Batch wake-up logic — still fires when `active_count == 0`
- ActivityBar agent count spinner — still uses `active_count`

## Constraints

- `dispatch()` return type: `int` on success, `str` on error
- `_settled` guard stays per-name (if agent failed this turn, all re-dispatches blocked)
- `cancel(name)` cancels ALL instances with that name
- No new user-facing concepts — run IDs are internal plumbing
- Existing tests must pass or be intentionally updated
